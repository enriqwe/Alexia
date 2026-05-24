#!/usr/bin/env python3
"""Detecta importes raros en facturas Alexia comparando con histórico.

Uso:
  analyze_invoice_anomalies.py facturas.json new_guids.txt

La idea es revisar las líneas de las facturas nuevas contra importes históricos
por concepto y por niño. Clasifica:
- ANOMALÍA: concepto históricamente estable cuyo importe se desvía.
- REVISAR: concepto nuevo o con poco histórico/variable.
- OK: conceptos conocidos con importes habituales.
"""
from __future__ import annotations

import json
import re
import statistics
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CENT = 0.01
ABS_TOLERANCE = 2.0
REL_TOLERANCE = 0.10
MIN_STABLE_COUNT = 3


def euro_to_float(s: Any) -> float:
    s = str(s or '').replace('€', '').strip()
    if not re.search(r'\d', s):
        return 0.0
    return float(s.replace('.', '').replace(',', '.'))


def money(v: float) -> str:
    return f"{v:,.2f} €".replace(',', 'X').replace('.', ',').replace('X', '.')


def norm_name(name: str) -> str:
    n = str(name or '').upper().strip()
    n = (n.replace('Á', 'A').replace('É', 'E').replace('Í', 'I')
           .replace('Ó', 'O').replace('Ú', 'U').replace('Ü', 'U'))
    n = re.sub(r'\s+', ' ', n)
    # Regularizaciones y variantes con numeración suelen ser el mismo concepto.
    n = re.sub(r'\bREGULARIZACION\b', 'REGULARIZACION', n)
    n = re.sub(r'\s+\d+$', '', n)
    return n


def invoice_amount(inv: dict[str, Any]) -> float:
    return float(inv.get('importeNumero') or euro_to_float(inv.get('importe')))


def invoice_date(inv: dict[str, Any]) -> str:
    return str(inv.get('fechaIso') or '')


def invoice_lines(inv: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for l in inv.get('detail', {}).get('lines') or []:
        name = str(l.get('nombre') or '').strip()
        if not name or name.lower() == 'nombre':
            continue
        rows.append({
            'name': name,
            'norm': norm_name(name),
            'amount': euro_to_float(l.get('importeTotal')),
            'raw': l,
        })

    # Alexia a veces duplica las líneas en el detalle: recortamos cuando la suma
    # ya cuadra con el total de factura y eliminamos duplicados exactos por mitades.
    expected_total = invoice_amount(inv)
    if rows:
        running = 0.0
        min_idx = 2 if abs(expected_total) < CENT else 1
        for idx, row in enumerate(rows, start=1):
            running += row['amount']
            if idx >= min_idx and abs(running - expected_total) < CENT:
                rows = rows[:idx]
                break
    if len(rows) % 2 == 0:
        mid = len(rows) // 2
        if [(r['norm'], round(r['amount'], 2)) for r in rows[:mid]] == [(r['norm'], round(r['amount'], 2)) for r in rows[mid:]]:
            rows = rows[:mid]
    return rows


@dataclass
class Baseline:
    count: int
    values: list[float]
    modes: list[tuple[float, int]]
    median: float
    stable: bool


def build_baseline(invoices: list[dict[str, Any]], before_date: str, exclude_guids: set[str]) -> dict[tuple[str, str], Baseline]:
    values: dict[tuple[str, str], list[float]] = defaultdict(list)
    for inv in invoices:
        if inv.get('guid') in exclude_guids:
            continue
        if before_date and invoice_date(inv) and invoice_date(inv) >= before_date:
            continue
        child = str(inv.get('childName') or inv.get('beneficiario') or 'Alumno')
        for line in invoice_lines(inv):
            amount = round(float(line['amount']), 2)
            if abs(amount) < CENT:
                continue
            # Baseline específica del niño y global para fallback.
            values[(child, line['norm'])].append(amount)
            values[('*', line['norm'])].append(amount)

    out: dict[tuple[str, str], Baseline] = {}
    for key, vals in values.items():
        rounded = [round(v, 2) for v in vals]
        c = Counter(rounded)
        modes = sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))[:5]
        median = statistics.median(rounded)
        # Estable si hay suficiente histórico y casi siempre el mismo importe,
        # o si la dispersión relativa es baja.
        top_value, top_count = modes[0]
        avg = sum(rounded) / len(rounded)
        stdev = statistics.pstdev(rounded) if len(rounded) > 1 else 0.0
        stable = len(rounded) >= MIN_STABLE_COUNT and (
            top_count / len(rounded) >= 0.70 or (avg and stdev / abs(avg) <= 0.05)
        )
        out[key] = Baseline(len(rounded), rounded, modes, median, stable)
    return out


def check_amount(amount: float, baseline: Baseline | None) -> tuple[str, str]:
    if baseline is None:
        return 'REVISAR', 'concepto sin histórico previo'
    amount = round(amount, 2)
    habitual = [v for v, _ in baseline.modes]
    if any(abs(amount - v) <= CENT for v in habitual):
        return 'OK', f'importe habitual ({baseline.count} muestras)'
    if not baseline.stable:
        opts = ', '.join(money(v) for v, _ in baseline.modes[:3])
        return 'REVISAR', f'concepto variable/poco estable; importes vistos: {opts}'
    expected = baseline.modes[0][0]
    diff = abs(amount - expected)
    rel = diff / abs(expected) if expected else 1.0
    if diff > ABS_TOLERANCE and rel > REL_TOLERANCE:
        return 'ANOMALÍA', f'esperado aprox. {money(expected)}; diferencia {money(amount - expected)}'
    return 'OK', f'ligera variación frente a {money(expected)}'


def analyze(data: dict[str, Any], new_guids: set[str]) -> dict[str, Any]:
    invoices = data.get('invoices', [])
    targets = [i for i in invoices if i.get('guid') in new_guids] if new_guids else []
    targets.sort(key=lambda x: (invoice_date(x), x.get('childName', ''), x.get('factura', '')))
    findings: list[dict[str, Any]] = []
    counts = Counter()

    for inv in targets:
        child = str(inv.get('childName') or inv.get('beneficiario') or 'Alumno')
        baseline = build_baseline(invoices, invoice_date(inv), new_guids)
        line_total = 0.0
        lines = invoice_lines(inv)
        for line in lines:
            line_total += line['amount']
            b = baseline.get((child, line['norm'])) or baseline.get(('*', line['norm']))
            status, reason = check_amount(line['amount'], b)
            counts[status] += 1
            if status != 'OK':
                findings.append({
                    'status': status,
                    'child': child,
                    'factura': inv.get('factura', ''),
                    'fecha': invoice_date(inv),
                    'concepto': line['name'],
                    'importe': line['amount'],
                    'reason': reason,
                })
        inv_total = invoice_amount(inv)
        if lines and abs(line_total - inv_total) > 0.05:
            counts['ANOMALÍA'] += 1
            findings.append({
                'status': 'ANOMALÍA',
                'child': child,
                'factura': inv.get('factura', ''),
                'fecha': invoice_date(inv),
                'concepto': 'TOTAL FACTURA vs líneas',
                'importe': inv_total,
                'reason': f'las líneas suman {money(line_total)} pero la factura indica {money(inv_total)}',
            })

    return {
        'checkedInvoices': len(targets),
        'checkedLines': sum(counts.values()),
        'counts': dict(counts),
        'findings': findings,
    }


def print_report(result: dict[str, Any]) -> None:
    checked = result['checkedInvoices']
    if checked == 0:
        print('Control de importes: no hay facturas nuevas que analizar.')
        return
    counts = Counter(result.get('counts') or {})
    anomalies = counts.get('ANOMALÍA', 0)
    review = counts.get('REVISAR', 0)
    ok = counts.get('OK', 0)
    print(f"Control de importes: {checked} factura(s), {ok} línea(s) OK, {review} para revisar, {anomalies} anomalía(s).")
    if not result.get('findings'):
        print('Resultado: todos los importes coinciden con patrones habituales.')
        return
    for f in result['findings']:
        print(f"- {f['status']}: {f['child']} · {f['factura']} · {f['concepto']} · {money(f['importe'])} — {f['reason']}")


def main() -> int:
    if len(sys.argv) != 3:
        print('Uso: analyze_invoice_anomalies.py facturas.json new_guids.txt', file=sys.stderr)
        return 2
    data = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
    new_guids = {x.strip() for x in Path(sys.argv[2]).read_text(encoding='utf-8').splitlines() if x.strip()}
    result = analyze(data, new_guids)
    print_report(result)
    return 1 if result.get('counts', {}).get('ANOMALÍA', 0) else 0


if __name__ == '__main__':
    raise SystemExit(main())

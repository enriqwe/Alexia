#!/usr/bin/env python3
import json, re, sys
from collections import defaultdict
from pathlib import Path


def euro_to_float(s):
    s = str(s or '').replace('€', '').strip()
    if not re.search(r'\d', s):
        return 0.0
    return float(s.replace('.', '').replace(',', '.'))


def money(v):
    return f"{v:,.2f} €".replace(',', 'X').replace('.', ',').replace('X', '.')


def category(name):
    n = str(name or '').upper()
    if 'LIBROS' in n:
        return 'Libros'
    if 'COMEDOR' in n:
        return 'Comedor'
    if 'AMPLIACIÓN' in n or 'AMPLIACION' in n:
        return 'Ampliación horaria'
    if n.startswith('C.D.') or n.startswith('E.M.') or any(x in n for x in ['ALOHA', 'KÁRATE', 'KARATE', 'NATACIÓN', 'NATACION', 'AJEDREZ', 'TENIS', 'PIANO', 'ROBÓTICA', 'ROBOTICA', 'DANZA', 'MÚSICA', 'MUSICA']):
        return 'Extraescolares'
    if any(x in n for x in ['ACTIVIDAD COMPLEMENTARIA', 'AULA NATURALEZA', 'BUITRAGO', 'EXCURSI', 'SALIDA']):
        return 'Actividades complementarias'
    if any(x in n for x in ['SALUD', 'PSICOPEDAG', 'GABINETE', 'ENFERMER']):
        return 'Salud / gabinete'
    if any(x in n for x in ['MATERIAL', 'FOTOGRAF', 'SEGURO', 'DIGITAL', 'AGENDA', 'ENVÍO', 'ENVIO']):
        return 'Material / seguros'
    return 'Otros'


def invoice_amount(inv):
    return float(inv.get('importeNumero') or euro_to_float(inv.get('importe')))


def invoice_lines(inv):
    rows = []
    for l in inv.get('detail', {}).get('lines') or []:
        name = str(l.get('nombre') or '').strip()
        if not name or name.lower() == 'nombre':
            continue
        rows.append((name, euro_to_float(l.get('importeTotal')), category(name)))

    expected_total = invoice_amount(inv)
    if rows:
        running = 0.0
        min_idx = 2 if abs(expected_total) < 0.01 else 1
        for idx, row in enumerate(rows, start=1):
            running += row[1]
            if idx >= min_idx and abs(running - expected_total) < 0.01:
                rows = rows[:idx]
                break

    if len(rows) % 2 == 0:
        mid = len(rows) // 2
        if [(r[0], r[1]) for r in rows[:mid]] == [(r[0], r[1]) for r in rows[mid:]]:
            rows = rows[:mid]
    return rows


def main():
    if len(sys.argv) != 3:
        print('Uso: generate_invoice_summary.py facturas.json new_guids.txt', file=sys.stderr)
        return 2
    data = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
    new = {x.strip() for x in Path(sys.argv[2]).read_text(encoding='utf-8').splitlines() if x.strip()}
    items = [i for i in data.get('invoices', []) if i.get('guid') in new]
    items.sort(key=lambda x: (x.get('fechaIso', ''), x.get('childName', ''), x.get('factura', '')))

    monthly = defaultdict(float)
    for inv in data.get('invoices', []):
        monthly[inv.get('fechaIso', '')[:7]] += invoice_amount(inv)

    new_total = sum(invoice_amount(i) for i in items)
    by_child = defaultdict(float)
    by_cat = defaultdict(float)
    new_months = sorted({i.get('fechaIso', '')[:7] for i in items if i.get('fechaIso')})
    for inv in items:
        inv_total = invoice_amount(inv)
        by_child[inv.get('childName') or inv.get('beneficiario') or 'Alumno'] += inv_total
        lines = invoice_lines(inv)
        line_total = sum(amount for _, amount, _ in lines)
        scale = inv_total / line_total if abs(line_total) > 0.01 and abs(line_total - inv_total) > 0.01 else 1
        for _, amount, cat in lines:
            by_cat[cat] += amount * scale

    print(f"Nuevas facturas: {len(items)}")
    print(f"Importe nuevo: {money(new_total)}")
    if by_child:
        print('Por niño: ' + ' · '.join(f"{k}: {money(v)}" for k, v in sorted(by_child.items())))
    if by_cat:
        top = sorted(by_cat.items(), key=lambda x: x[1], reverse=True)[:5]
        print('Categorías: ' + ' · '.join(f"{k}: {money(v)}" for k, v in top))

    for month in new_months:
        prev_values = [v for m, v in monthly.items() if m < month]
        avg = sum(prev_values[-6:]) / min(len(prev_values), 6) if prev_values else 0
        current = monthly[month]
        if avg and abs(current - avg) / avg >= 0.25:
            direction = 'por encima' if current > avg else 'por debajo'
            print(f"Anomalía: {month} queda {direction} de la media reciente ({money(current)} vs {money(avg)}).")
        else:
            print(f"Patrón mensual: {month} suma {money(current)}; sin desviación fuerte frente a la media reciente.")

    for i in items:
        print(f"- {i.get('childName','Alumno')}: {i.get('factura','')} · {i.get('fechaIso','')} · {i.get('importe','')}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

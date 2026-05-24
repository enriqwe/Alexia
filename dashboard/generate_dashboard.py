#!/usr/bin/env python3
import json, re, statistics
from pathlib import Path
from collections import defaultdict, Counter
from datetime import datetime

ROOT = Path(__file__).resolve().parent
DATA = json.loads((ROOT / 'facturas.json').read_text(encoding='utf-8'))


def euro_to_float(s):
    s = str(s or '').replace('€', '').strip()
    if not re.search(r'\d', s):
        return 0.0
    return float(s.replace('.', '').replace(',', '.'))


def money(v):
    return f"{v:,.2f} €".replace(',', 'X').replace('.', ',').replace('X', '.')


def clean_lines(lines, expected_total=None):
    rows = []
    for l in lines or []:
        name = str(l.get('nombre') or '').strip()
        if not name or name.lower() == 'nombre':
            continue
        rows.append({
            'nombre': re.sub(r'\s+', ' ', name),
            'unidades': str(l.get('unidades') or '').strip(),
            'importeUnitario': str(l.get('importeUnitario') or '').strip(),
            'importeTotal': str(l.get('importeTotal') or '').strip(),
            'importeNumero': euro_to_float(l.get('importeTotal')),
        })

    # Alexia sometimes renders extra/duplicated rows in the invoice detail table.
    # The common comedor case is: real invoice rows first, then duplicated sibling rows
    # (or other repeated rows). Keep the shortest leading block that reconciles with
    # the invoice total, so category totals do not double-count comedor/ampliación.
    if expected_total is not None and rows:
        running = 0.0
        min_idx = 2 if abs(expected_total) < 0.01 else 1
        for idx, row in enumerate(rows, start=1):
            running += row['importeNumero']
            if idx >= min_idx and abs(running - expected_total) < 0.01:
                rows = rows[:idx]
                break

    if len(rows) % 2 == 0:
        mid = len(rows) // 2
        left = [(r['nombre'], r['importeTotal']) for r in rows[:mid]]
        right = [(r['nombre'], r['importeTotal']) for r in rows[mid:]]
        if left == right:
            rows = rows[:mid]
    return rows


def category(name):
    n = name.upper()
    if 'LIBROS' in n:
        return 'Libros'
    if 'COMEDOR' in n:
        return 'Comedor'
    if 'AMPLIACIÓN' in n or 'AMPLIACION' in n:
        return 'Ampliación horaria'
    if n.startswith('C.D.') or n.startswith('E.M.') or 'ALOHA' in n or 'KÁRATE' in n or 'KARATE' in n or 'NATACIÓN' in n or 'NATACION' in n or 'AJEDREZ' in n or 'TENIS' in n or 'PIANO' in n or 'ROBÓTICA' in n or 'ROBOTICA' in n or 'DANZA' in n or 'MÚSICA' in n or 'MUSICA' in n:
        return 'Extraescolares'
    if 'ACTIVIDAD COMPLEMENTARIA' in n or 'AULA NATURALEZA' in n or 'BUITRAGO' in n or 'EXCURSI' in n or 'SALIDA' in n:
        return 'Actividades complementarias'
    if 'SALUD' in n or 'PSICOPEDAG' in n or 'GABINETE' in n or 'ENFERMER' in n:
        return 'Salud / gabinete'
    if 'MATERIAL' in n or 'FOTOGRAF' in n or 'SEGURO' in n or 'DIGITAL' in n or 'AGENDA' in n or 'ENVÍO' in n or 'ENVIO' in n:
        return 'Material / seguros'
    return 'Otros'


def pct_delta(now, prev):
    if prev == 0:
        return None
    return (now - prev) / prev * 100


def safe_month_label(m):
    try:
        return datetime.strptime(m, '%Y-%m').strftime('%m/%Y')
    except Exception:
        return m


invoices = []
for inv in DATA['invoices']:
    invoice_total = inv['importeNumero']
    lines = clean_lines(inv.get('detail', {}).get('lines'), invoice_total)
    invoices.append({
        'factura': inv['factura'],
        'childName': inv.get('childName', inv.get('beneficiario', 'Alumno')),
        'fechaIso': inv['fechaIso'],
        'fecha': inv['fechaEmision'],
        'mes': inv['fechaIso'][:7],
        'year': inv['fechaIso'][:4],
        'estado': inv['estado'],
        'titular': inv['titular'],
        'beneficiario': inv['beneficiario'],
        'importe': invoice_total,
        'importeTexto': inv['importe'],
        'pdf': inv.get('pdf', {}).get('file', ''),
        'lines': [{**l, 'categoria': category(l['nombre'])} for l in lines],
        'lineSum': sum(l['importeNumero'] for l in lines),
    })

monthly = defaultdict(float)
monthly_child = defaultdict(lambda: defaultdict(float))
monthly_cat = defaultdict(lambda: defaultdict(float))
concepts = defaultdict(float)
concept_count = Counter()
categories = defaultdict(float)
by_child = defaultdict(float)
years = defaultdict(float)

for inv in invoices:
    monthly[inv['mes']] += inv['importe']
    monthly_child[inv['mes']][inv['childName']] += inv['importe']
    by_child[inv['childName']] += inv['importe']
    years[inv['year']] += inv['importe']
    for l in inv['lines']:
        concepts[l['nombre']] += l['importeNumero']
        concept_count[l['nombre']] += 1
        categories[l['categoria']] += l['importeNumero']
        monthly_cat[inv['mes']][l['categoria']] += l['importeNumero']

months = sorted(monthly)
values = [monthly[m] for m in months]
total = sum(inv['importe'] for inv in invoices)
avg_month = total / len(months) if months else 0
median_month = statistics.median(values) if values else 0
max_month = max(months, key=lambda m: monthly[m]) if months else ''
min_month = min(months, key=lambda m: monthly[m]) if months else ''
latest_month = months[-1] if months else ''
previous_month = months[-2] if len(months) > 1 else ''
latest_delta = pct_delta(monthly[latest_month], monthly[previous_month]) if latest_month and previous_month else None
latest_top_cat = max(monthly_cat[latest_month].items(), key=lambda x: x[1])[0] if latest_month and monthly_cat[latest_month] else ''

# Month-over-month changes for alerts
mom = []
for i in range(1, len(months)):
    d = pct_delta(monthly[months[i]], monthly[months[i-1]])
    mom.append({'month': months[i], 'prevMonth': months[i-1], 'deltaPct': d, 'deltaAbs': monthly[months[i]] - monthly[months[i-1]]})
biggest_jump = max(mom, key=lambda x: x['deltaAbs']) if mom else None
biggest_drop = min(mom, key=lambda x: x['deltaAbs']) if mom else None

sorted_concepts = sorted(concepts.items(), key=lambda x: x[1], reverse=True)
sorted_categories = sorted(categories.items(), key=lambda x: x[1], reverse=True)
top_concept = sorted_concepts[0] if sorted_concepts else ('', 0)
top_category = sorted_categories[0] if sorted_categories else ('', 0)

insights = []
if latest_month:
    trend_word = 'sube' if (latest_delta or 0) > 5 else 'baja' if (latest_delta or 0) < -5 else 'se mantiene estable'
    delta_txt = 'sin comparación previa' if latest_delta is None else f"{latest_delta:+.1f}% vs {safe_month_label(previous_month)}"
    insights.append({
        'title': f"Último mes: {money(monthly[latest_month])}",
        'body': f"{safe_month_label(latest_month)} {trend_word}; {delta_txt}. La categoría que más pesa es {latest_top_cat}.",
        'tone': 'warn' if (latest_delta or 0) > 10 else 'good' if (latest_delta or 0) < -10 else 'neutral'
    })
if top_category[0]:
    insights.append({
        'title': f"Mayor bolsa de gasto: {top_category[0]}",
        'body': f"Acumula {money(top_category[1])}, el {top_category[1] / total * 100:.1f}% del total analizado.",
        'tone': 'neutral'
    })
if top_concept[0]:
    insights.append({
        'title': f"Concepto dominante: {top_concept[0]}",
        'body': f"Suma {money(top_concept[1])} en {concept_count[top_concept[0]]} líneas de factura.",
        'tone': 'neutral'
    })
if biggest_jump and biggest_jump['deltaAbs'] > 0:
    insights.append({
        'title': f"Mayor subida detectada: {safe_month_label(biggest_jump['month'])}",
        'body': f"Aumentó {money(biggest_jump['deltaAbs'])} respecto a {safe_month_label(biggest_jump['prevMonth'])}.",
        'tone': 'warn'
    })

payload = {
    'generatedAt': DATA['generatedAt'],
    'months': [{'month': m, 'total': round(monthly[m], 2), 'cats': dict(monthly_cat[m]), 'children': dict(monthly_child[m])} for m in months],
    'years': [{'year': y, 'total': round(v, 2)} for y, v in sorted(years.items())],
    'concepts': [{'name': k, 'total': round(v, 2), 'count': concept_count[k], 'category': category(k)} for k, v in sorted_concepts],
    'categories': [{'name': k, 'total': round(v, 2), 'share': v / total * 100 if total else 0} for k, v in sorted_categories],
    'children': [{'name': k, 'total': round(v, 2), 'share': v / total * 100 if total else 0} for k, v in sorted(by_child.items(), key=lambda x: x[0])],
    'invoices': invoices,
    'insights': insights,
    'kpis': {
        'total': round(total, 2),
        'invoiceCount': len(invoices),
        'monthCount': len(months),
        'avgMonth': round(avg_month, 2),
        'medianMonth': round(median_month, 2),
        'maxMonth': max_month,
        'maxMonthTotal': round(monthly[max_month], 2) if max_month else 0,
        'minMonth': min_month,
        'minMonthTotal': round(monthly[min_month], 2) if min_month else 0,
        'latestMonth': latest_month,
        'latestMonthTotal': round(monthly[latest_month], 2) if latest_month else 0,
        'latestDeltaPct': latest_delta,
        'topConcept': top_concept[0],
        'topConceptTotal': round(top_concept[1], 2),
        'topCategory': top_category[0],
        'topCategoryTotal': round(top_category[1], 2),
    }
}

payload_json = json.dumps(payload, ensure_ascii=False).replace('</script>', '<\\/script>')

html_template = r'''<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Centro de mando · Facturas Alexia</title>
<style>
:root{--bg:#080d1a;--panel:#111a2e;--panel2:#16233e;--line:#263655;--text:#eef4ff;--muted:#95a5c7;--soft:#c7d4f2;--accent:#7c5cff;--accent2:#18c7a7;--warn:#ffb020;--bad:#ff5d73;--good:#45d483;--blue:#4dabf7}*{box-sizing:border-box}body{margin:0;font-family:Inter,ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif;background:radial-gradient(circle at 0 0,#203365 0,#080d1a 44%);color:var(--text)}a{color:#9cc8ff}.wrap{width:min(1480px,100%);margin:0 auto;padding:22px}.hero{display:grid;grid-template-columns:1fr auto;gap:18px;align-items:start;margin-bottom:18px}h1{margin:0;font-size:clamp(29px,4vw,50px);letter-spacing:-.045em}.sub{color:var(--muted);margin-top:8px;line-height:1.45;max-width:900px}.badge,.pill{display:inline-block;border:1px solid #334360;background:#101a30;border-radius:999px;color:#c8d5f5}.badge{padding:9px 12px;white-space:nowrap}.pill{padding:3px 8px;font-size:12px}.grid{display:grid;gap:16px}.kpis{grid-template-columns:repeat(6,minmax(0,1fr))}.card{background:linear-gradient(180deg,rgba(255,255,255,.052),rgba(255,255,255,.022));border:1px solid rgba(255,255,255,.09);box-shadow:0 18px 50px #0006;border-radius:22px;padding:18px;overflow:hidden}.card.tight{padding:14px}.kpi .label{color:var(--muted);font-size:13px}.kpi .value{font-size:clamp(24px,3vw,35px);font-weight:850;margin-top:8px;letter-spacing:-.035em}.kpi .hint{color:#b8c4df;margin-top:8px;font-size:13px}.delta{font-weight:800}.delta.good{color:var(--good)}.delta.bad{color:var(--bad)}.delta.neutral{color:var(--muted)}.command{grid-template-columns:1.15fr .85fr;margin-top:16px}.main{grid-template-columns:1.42fr .9fr;align-items:stretch;margin-top:16px}.two{grid-template-columns:1fr 1fr;margin-top:16px}h2{margin:0 0 13px;font-size:20px;letter-spacing:-.02em}.section-head{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:12px}.chart{width:100%;height:370px}.chart.small{height:370px}.chart.flow{height:720px;min-height:720px}.insights{display:grid;gap:10px}.insight{border:1px solid #2b3a5c;background:#0d1528;border-radius:16px;padding:13px}.insight strong{display:block;margin-bottom:5px}.insight.good{border-color:#27684a}.insight.warn{border-color:#70551d}.insight.bad{border-color:#713043}.quick{display:grid;grid-template-columns:repeat(2,1fr);gap:10px}.quick .answer{background:#0d1528;border:1px solid #2b3a5c;border-radius:16px;padding:13px}.answer .small{color:var(--muted);font-size:12px}.answer .big{font-weight:850;font-size:22px;margin-top:4px}.finance-grid{grid-template-columns:1.2fr 1fr 1fr;margin-top:16px}.explain-grid{grid-template-columns:1fr 1fr;margin-top:16px}.mini-list{display:grid;gap:9px}.mini-item{border:1px solid #2b3a5c;background:#0d1528;border-radius:14px;padding:11px}.mini-item strong{display:block;margin-bottom:4px}.mini-item.warn{border-color:#70551d}.mini-item.bad{border-color:#713043}.explain-chart{height:260px}.explain-text{border-top:1px solid rgba(255,255,255,.08);margin-top:10px;padding-top:10px;color:#b9c6e4;font-size:13px;line-height:1.45}.explain-text strong{color:#eef4ff}.metric-row{display:grid;grid-template-columns:1fr auto;gap:10px;align-items:center;border-bottom:1px solid rgba(255,255,255,.07);padding:8px 0}.metric-row:last-child{border-bottom:0}.meter{height:9px;background:#20304f;border-radius:999px;overflow:hidden;margin-top:7px}.meter span{display:block;height:100%;border-radius:999px;background:linear-gradient(90deg,var(--accent2),var(--accent))}.controls{display:flex;gap:10px;flex-wrap:wrap;margin:12px 0 16px}.toolbar{display:flex;gap:8px;flex-wrap:wrap}.multi{position:relative;min-width:260px}.multi-btn{width:100%;min-height:42px;display:flex;align-items:center;justify-content:space-between;gap:10px;background:linear-gradient(180deg,#121d34,#0d1426);border-color:#344568}.multi-btn.active{border-color:var(--accent);box-shadow:0 0 0 3px rgba(124,92,255,.16)}.multi-btn-text{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.multi-menu{display:none;position:absolute;z-index:50;top:calc(100% + 8px);left:0;width:min(360px,92vw);max-height:430px;overflow:auto;padding:10px;background:linear-gradient(180deg,#121d34,#0b1222);border:1px solid #35486e;border-radius:18px;box-shadow:0 24px 70px #000b}.multi.open .multi-menu{display:block}.multi-actions{display:flex;gap:8px;margin-bottom:8px}.multi-actions button{flex:1;padding:8px 10px;border-radius:10px;font-size:12px}.multi-option{display:grid;grid-template-columns:22px 10px 1fr;gap:10px;align-items:center;padding:9px 10px;border-radius:13px;color:#dbe6ff;cursor:pointer}.multi-option:hover{background:rgba(255,255,255,.055)}.multi-option input{min-width:auto;accent-color:var(--accent)}.multi-option .swatch{width:10px;height:10px;border-radius:999px}.multi-option .count{color:var(--muted);font-size:12px}select,input,button{background:#0d1426;color:var(--text);border:1px solid #2f3d60;border-radius:12px;padding:10px 12px;outline:none}button{cursor:pointer}button:hover{border-color:#5870aa}input{min-width:230px;flex:1}.multi-option input{min-width:auto;flex:0;padding:0}table{width:100%;border-collapse:collapse;font-size:14px}th,td{border-bottom:1px solid rgba(255,255,255,.08);padding:10px 8px;text-align:left;vertical-align:top}th{color:#b9c6e4;font-size:12px;text-transform:uppercase;letter-spacing:.05em}.num{text-align:right;font-variant-numeric:tabular-nums}.concept{display:flex;align-items:center;gap:9px}.dot{width:10px;height:10px;border-radius:99px;display:inline-block}.invoice-row{cursor:pointer}.invoice-row:hover{background:rgba(255,255,255,.04)}.details{display:none;background:#0d1426}.details.open{display:table-row}.details ul{margin:0;padding-left:18px;color:#d7e1f8}.statusline{color:var(--muted);font-size:13px}.footer{color:var(--muted);margin:24px 0 8px;font-size:13px}.heat{display:grid;gap:8px}.heat-row{display:grid;grid-template-columns:96px 1fr 90px;gap:10px;align-items:center}.heat-bar{height:12px;border-radius:99px;background:#22304f;overflow:hidden}.heat-fill{height:100%;background:linear-gradient(90deg,var(--accent2),var(--accent))}.price-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px;width:100%;align-items:stretch}.price-card{background:#0d1528;border:1px solid #2b3a5c;border-radius:16px;padding:14px;width:100%;min-width:0}.price-card .name{font-weight:800}.price-card .amount{font-size:24px;font-weight:900;margin-top:8px}.price-card .meta{color:var(--muted);font-size:12px;margin-top:6px}.money-map{display:grid;grid-template-columns:260px 1fr;gap:18px;align-items:stretch}.money-total{background:linear-gradient(180deg,#18c7a7,#0b927c);color:#06131b;border-radius:22px;padding:22px;display:flex;flex-direction:column;justify-content:center;min-height:220px}.money-total .label{font-size:13px;font-weight:800;text-transform:uppercase;opacity:.75}.money-total .value{font-size:34px;font-weight:950;margin-top:10px;letter-spacing:-.04em}.money-total .meta{font-size:13px;margin-top:8px;opacity:.8}.money-cats{display:grid;gap:12px}.money-cat{background:#0d1528;border:1px solid #2b3a5c;border-radius:18px;padding:14px}.money-cat-head{display:grid;grid-template-columns:minmax(130px,1fr) auto auto;gap:12px;align-items:center}.money-cat-name{font-weight:850}.money-cat-amount{font-weight:850}.money-share{color:var(--muted);font-size:12px;text-align:right}.money-bar{height:12px;background:#20304f;border-radius:999px;overflow:hidden;margin-top:10px}.money-fill{height:100%;border-radius:999px}.money-concepts{display:grid;gap:7px;margin-top:12px}.money-concept{display:grid;grid-template-columns:minmax(160px,1fr) minmax(90px,30%) 76px;gap:8px;align-items:center;color:#d8e2f6;font-size:12px}.money-concept-track{height:8px;background:#1e2c49;border-radius:99px;overflow:hidden}.money-concept-fill{height:100%;border-radius:99px}.money-note{color:var(--muted);font-size:12px;margin-top:10px}.donut-box{height:100%;min-height:340px}.mobile-note{display:none;color:var(--muted);font-size:13px}@media(max-width:1050px){.wrap{padding:14px}.hero{display:block}.badge{margin-top:12px}.kpis,.command,.main,.two,.finance-grid,.explain-grid,.price-grid,.money-map{grid-template-columns:1fr}.quick{grid-template-columns:1fr}.chart{height:300px}table{font-size:13px}th:nth-child(5),td:nth-child(5){display:none}.mobile-note{display:block}}@media(max-width:560px){th:nth-child(4),td:nth-child(4){display:none}.card{border-radius:18px;padding:14px}}
</style>
</head>
<body>
<div class="wrap">
  <header class="hero">
    <div>
      <h1>Centro de mando de gastos Alexia</h1>
      <div class="controls" style="margin:14px 0 0">
        <input id="search" placeholder="Buscar concepto, factura, niño, mes…">
        <input id="dateFrom" type="date" title="Desde">
        <input id="dateTo" type="date" title="Hasta">
        <select id="childFilter"><option value="">Todos los niños</option></select>
        <div class="multi" id="categoryFilter">
          <button id="categoryButton" class="multi-btn" type="button"><span id="categoryButtonText" class="multi-btn-text">Todas las categorías</span><span>⌄</span></button>
          <div class="multi-menu" id="categoryMenu">
            <div class="multi-actions"><button id="selectAllCategories" type="button">Seleccionar todas</button><button id="clearCategories" type="button">Limpiar</button></div>
            <div id="categoryOptions"></div>
          </div>
        </div>
        <select id="monthFilter"><option value="">Todos los meses</option></select>
        <button id="currentSchoolYear">Curso actual</button><button id="allDates">Todo</button><button id="saveView">Guardar vista</button><button id="resetView">Limpiar filtros</button><button id="exportCsv">Exportar CSV</button>
      </div>
      <div class="statusline" id="filterStatus" style="margin-top:8px"></div>
    </div>
    <div class="badge" id="generated"></div>
  </header>

  <section class="card" style="margin-top:16px">
    <div class="section-head"><h2>Datos principales</h2><button id="toggleKpis" type="button">Mostrar</button></div>
    <div id="kpiSection" style="display:none">
      <section class="grid kpis">
        <div class="card tight kpi"><div class="label">Total analizado</div><div class="value" id="kTotal"></div><div class="hint" id="kTotalHint"></div></div>
        <div class="card tight kpi"><div class="label">Media mensual</div><div class="value" id="kAvg"></div><div class="hint" id="kMedian"></div></div>
        <div class="card tight kpi"><div class="label">Último mes</div><div class="value" id="kLatest"></div><div class="hint" id="kLatestHint"></div></div>
        <div class="card tight kpi"><div class="label">Mes más caro</div><div class="value" id="kMax"></div><div class="hint" id="kMaxHint"></div></div>
        <div class="card tight kpi"><div class="label">Categoría principal</div><div class="value" id="kTopCat"></div><div class="hint" id="kTopCatHint"></div></div>
        <div class="card tight kpi"><div class="label">Por niño</div><div class="value" id="kChildren" style="font-size:18px;line-height:1.35"></div><div class="hint">reparto acumulado</div></div>
      </section>
    </div>
  </section>

  <section class="card" style="margin-top:16px">
    <div class="section-head"><h2>Recibos recibidos del mes actual</h2><span class="statusline" id="currentMonthStatus"></span></div>
    <div style="overflow:auto"><table id="currentMonthTable"><thead><tr><th>Fecha</th><th>Factura</th><th>Niño</th><th>Conceptos</th><th class="num">Importe</th><th>PDF</th></tr></thead><tbody></tbody></table></div>
  </section>

  <section class="card" style="margin-top:16px">
    <div class="section-head"><h2>Cómo se ha ido el dinero</h2><span class="statusline">total → categorías → conceptos principales</span></div>
    <div id="moneyFlowChart" class="chart flow"></div>
  </section>

  <section class="grid main">
    <div class="card"><div class="section-head"><h2>Evolución mensual</h2><span class="statusline">barras = gasto total por mes</span></div><div id="monthlyChart" class="chart"></div></div>
    <div class="card"><div class="section-head"><h2>Reparto por categoría</h2></div><div id="donutChart" class="chart small"></div></div>
  </section>

  <section class="card" style="margin-top:16px">
    <div class="section-head"><h2>Cuánto cuesta cada actividad</h2><button id="togglePrices" type="button">Mostrar</button></div>
    <div id="priceSection" style="display:none">
      <div class="statusline" style="margin-bottom:12px">cuota habitual detectada según filtros</div>
      <div id="priceCards" class="price-grid"></div>
    </div>
  </section>

  <section class="card" style="margin-top:16px">
    <div class="section-head"><h2>Gráficos comparativos</h2><button id="toggleComparatives" type="button">Mostrar</button></div>
    <div id="comparativesSection" style="display:none">
      <section class="grid two">
        <div class="card tight"><div class="section-head"><h2>Ranking de conceptos</h2><span class="statusline">top 12 acumulado</span></div><div id="conceptChart" class="chart"></div></div>
        <div class="card tight"><div class="section-head"><h2>Mapa de concentración</h2><span class="statusline">meses más intensos</span></div><div id="heatChart" class="chart"></div></div>
      </section>

      <section class="grid two">
        <div class="card tight"><div class="section-head"><h2>Comparativa por niño</h2><span class="statusline">mensual apilado</span></div><div id="childrenChart" class="chart"></div></div>
        <div class="card tight"><div class="section-head"><h2>Comparativa mensual por curso escolar</h2><span class="statusline">septiembre → agosto</span></div><div id="yearChart" class="chart"></div></div>
      </section>
    </div>
  </section>

  <section class="card" style="margin-top:16px">
    <div class="section-head"><h2>Análisis financiero</h2><button id="toggleAnalysis" type="button">Mostrar</button></div>
    <div id="analysisSection" style="display:none">
      <section class="card tight" style="margin-top:12px">
        <div class="section-head"><h2>Respuestas rápidas</h2><span class="pill">según filtros</span></div>
        <div class="quick">
          <div class="answer"><div class="small">¿Dónde se va más?</div><div class="big" id="qWhere"></div><div class="small" id="qWhere2"></div></div>
          <div class="answer"><div class="small">¿Qué mes vigilar?</div><div class="big" id="qWatch"></div><div class="small" id="qWatch2"></div></div>
          <div class="answer"><div class="small">Factura media</div><div class="big" id="qInvoice"></div><div class="small">importe medio por factura</div></div>
          <div class="answer"><div class="small">Niño con más gasto</div><div class="big" id="qChild"></div><div class="small" id="qChild2"></div></div>
        </div>
      </section>

      <section class="grid finance-grid">
        <div class="card tight"><div class="section-head"><h2>Resumen ejecutivo</h2><span class="pill">lectura financiera</span></div><div id="executiveSummary" class="mini-list"></div></div>
        <div class="card tight"><div class="section-head"><h2>Alertas explicadas</h2><span class="statusline">desviación mensual</span></div><div id="anomalyChart" class="explain-chart"></div><div id="anomalyPanel" class="explain-text"></div></div>
        <div class="card tight"><div class="section-head"><h2>Proyección explicada</h2><span class="statusline">cierre de curso</span></div><div id="forecastChart" class="explain-chart"></div><div id="forecastPanel" class="explain-text"></div></div>
      </section>

      <section class="grid explain-grid">
        <div class="card tight"><div class="section-head"><h2>Recurrente vs puntual</h2><span class="statusline">cuotas estables frente a extras</span></div><div id="recurringChart" class="explain-chart"></div><div id="recurringPanel" class="explain-text"></div></div>
        <div class="card tight"><div class="section-head"><h2>Calidad de clasificación</h2><span class="statusline">datos que conviene vigilar</span></div><div id="qualityChart" class="explain-chart"></div><div id="qualityPanel" class="explain-text"></div></div>
      </section>
    </div>
  </section>

  <section class="card" style="margin-top:16px">
    <div class="section-head"><h2>Detalle y exploración</h2><span class="statusline">usa los filtros superiores</span></div>
    <div class="mobile-note">En móvil se ocultan algunas columnas; toca una factura para abrir el desglose.</div>
    <div class="statusline" id="tableStatus"></div>
    <div style="overflow:auto"><table id="invoiceTable"><thead><tr><th>Fecha</th><th>Factura</th><th>Niño</th><th>Conceptos</th><th>Beneficiario</th><th class="num">Importe</th><th>PDF</th></tr></thead><tbody></tbody></table></div>
  </section>

  <div class="footer">Nota: las categorías son agrupaciones analíticas generadas a partir del nombre del concepto; el detalle original queda en cada factura y PDF.</div>
</div>
<script src="vendor/echarts.min.js"></script>
<script id="data" type="application/json">__PAYLOAD__</script>
<script>
const DATA = JSON.parse(document.getElementById('data').textContent);
let activeCategories = [];
const colors = ['#7c5cff','#18c7a7','#ffb020','#ff5d73','#4dabf7','#45d483','#d67cff','#8aa4ff','#ff8f5a'];
const fmt = v => new Intl.NumberFormat('es-ES',{style:'currency',currency:'EUR'}).format(v || 0);
const pct = v => v == null || !isFinite(v) ? '—' : `${v>0?'+':''}${v.toFixed(1)}%`;
const monthLabel = m => { if(!m) return '—'; const [y,mo]=m.split('-'); return `${mo}/${y}`; };
const el = id => document.getElementById(id);
function svg(w,h,inner){return `<svg viewBox="0 0 ${w} ${h}" width="100%" height="100%" role="img">${inner}</svg>`}
function title(t,v){return `<title>${t}: ${fmt(v)}</title>`}
function deltaClass(v){return v == null || Math.abs(v)<5 ? 'neutral' : v>0 ? 'bad' : 'good'}
function truncate(s,n){return (s||'').length>n ? s.slice(0,n-1)+'…' : (s||'')}
function sum(arr, fn){return arr.reduce((a,x)=>a+(fn?fn(x):x),0)}
function uniq(arr){return [...new Set(arr)].filter(Boolean)}
function schoolYearDefaults(){
  const d = new Date(), y = d.getFullYear(), m = d.getMonth()+1;
  const startYear = m >= 9 ? y : y - 1;
  return {dateFrom:`${startYear}-09-01`, dateTo:`${startYear+1}-08-31`};
}
function selectedCategories(){return activeCategories}
function setSelectedCategories(values){activeCategories = [...new Set(values || [])].filter(Boolean)}
function toggleCategoryFilter(category){
  if(!category) return;
  activeCategories = activeCategories.length === 1 && activeCategories[0] === category ? [] : [category];
  persistDraft();
  renderAll();
}
function toggleCategoryChoice(category){
  const set=new Set(activeCategories);
  set.has(category) ? set.delete(category) : set.add(category);
  activeCategories=[...set];
  persistDraft();
  renderAll();
}
function categoryLabel(){
  const cats=selectedCategories();
  if(!cats.length) return 'Todas las categorías';
  if(cats.length===1) return cats[0];
  return `${cats.length} categorías seleccionadas`;
}
function toggleMonthFilter(month){
  if(!month) return;
  el('monthFilter').value = el('monthFilter').value === month ? '' : month;
  persistDraft();
  renderAll();
}
function currentFilters(){return {search:el('search').value,dateFrom:el('dateFrom').value,dateTo:el('dateTo').value,childFilter:el('childFilter').value,catFilter:selectedCategories(),monthFilter:el('monthFilter').value}}
function persistDraft(){localStorage.setItem('alexia-dashboard-draft', JSON.stringify(currentFilters()))}
function normalizeFilters(){
  // Evita el estado típico que deja el dashboard vacío: fecha inicial posterior a fecha final.
  if(el('dateFrom').value && el('dateTo').value && el('dateFrom').value > el('dateTo').value){
    const a=el('dateFrom').value; el('dateFrom').value=el('dateTo').value; el('dateTo').value=a;
  }
}
function clearNonDateFilters(){['search','childFilter','monthFilter'].forEach(id=>el(id).value=''); activeCategories=[]}
function baseFilteredInvoices({ignoreDate=false}={}){
  normalizeFilters();
  const f=currentFilters(), q=f.search.toLowerCase();
  return DATA.invoices.slice().sort((a,b)=>b.fechaIso.localeCompare(a.fechaIso)).filter(inv=>{
    const hay=(inv.factura+' '+inv.fecha+' '+inv.childName+' '+inv.beneficiario+' '+inv.lines.map(l=>l.nombre).join(' ')).toLowerCase();
    if(!ignoreDate && f.dateFrom && inv.fechaIso < f.dateFrom) return false;
    if(!ignoreDate && f.dateTo && inv.fechaIso > f.dateTo) return false;
    if(f.childFilter && inv.childName!==f.childFilter) return false;
    if(f.monthFilter && inv.mes!==f.monthFilter) return false;
    if(f.catFilter.length && !inv.lines.some(l=>f.catFilter.includes(l.categoria))) return false;
    if(q && !hay.includes(q)) return false;
    return true;
  })
}
function filteredInvoices(){return baseFilteredInvoices()}
function scopedLines(inv){const cats=selectedCategories(); return cats.length ? inv.lines.filter(l=>cats.includes(l.categoria)) : inv.lines}
function effectiveAmount(inv){return selectedCategories().length ? sum(scopedLines(inv), l=>l.importeNumero) : inv.importe}
function computeView(invs){
  const monthly={}, years={}, categories={}, concepts={}, conceptCount={}, children={};
  invs.forEach(inv=>{
    const amount = effectiveAmount(inv);
    monthly[inv.mes]=(monthly[inv.mes]||0)+amount;
    years[inv.year]=(years[inv.year]||0)+amount;
    children[inv.childName]=(children[inv.childName]||0)+amount;
    scopedLines(inv).forEach(l=>{
      categories[l.categoria]=(categories[l.categoria]||0)+l.importeNumero;
      concepts[l.nombre]=(concepts[l.nombre]||0)+l.importeNumero;
      conceptCount[l.nombre]=(conceptCount[l.nombre]||0)+1;
    })
  });
  const months=Object.keys(monthly).sort();
  const total=sum(invs,effectiveAmount), vals=months.map(m=>monthly[m]);
  const sortedVals=[...vals].sort((a,b)=>a-b), mid=Math.floor(sortedVals.length/2);
  const median=sortedVals.length ? (sortedVals.length%2?sortedVals[mid]:(sortedVals[mid-1]+sortedVals[mid])/2) : 0;
  const maxMonth=months.length ? months.reduce((a,b)=>monthly[a]>monthly[b]?a:b) : '';
  const latestMonth=months.at(-1)||'', prevMonth=months.at(-2)||'';
  const latestDeltaPct=latestMonth && prevMonth && monthly[prevMonth] ? (monthly[latestMonth]-monthly[prevMonth])/monthly[prevMonth]*100 : null;
  const cats=Object.entries(categories).sort((a,b)=>b[1]-a[1]).map(([name,total])=>({name,total,share:total/(sum(Object.values(categories))||1)*100}));
  const cons=Object.entries(concepts).sort((a,b)=>b[1]-a[1]).map(([name,total])=>({name,total,count:conceptCount[name],category:(DATA.concepts.find(c=>c.name===name)||{}).category||''}));
  const childs=Object.entries(children).sort((a,b)=>a[0].localeCompare(b[0])).map(([name,total])=>({name,total,share:total/(sum(Object.values(children))||1)*100}));
  const view={
    invoices:invs,total,
    months:months.map(m=>({month:m,total:monthly[m],children:Object.fromEntries(Object.keys(children).map(c=>[c,sum(invs.filter(i=>i.mes===m&&i.childName===c),effectiveAmount)]))})),
    years:Object.entries(years).sort().map(([year,total])=>({year,total})), categories:cats, concepts:cons, children:childs,
    kpis:{total,invoiceCount:invs.length,monthCount:months.length,avgMonth:months.length?total/months.length:0,medianMonth:median,maxMonth,maxMonthTotal:maxMonth?monthly[maxMonth]:0,latestMonth,latestMonthTotal:latestMonth?monthly[latestMonth]:0,latestDeltaPct,topCategory:cats[0]?.name||'—',topCategoryTotal:cats[0]?.total||0,topConcept:cons[0]?.name||'—',topConceptTotal:cons[0]?.total||0}
  };
  view.insights=makeInsights(view);
  return view;
}
function makeInsights(v){
  if(!v.invoices.length) return [{title:'Sin datos para estos filtros', body:'Amplía fechas o elimina filtros para ver métricas y gráficos.', tone:'warn'}];
  const k=v.kpis, latestCat=v.categories[0]?.name||'—', out=[];
  out.push({title:`Periodo filtrado: ${fmt(k.total)}`, body:`${k.invoiceCount} facturas en ${k.monthCount} meses. Media mensual ${fmt(k.avgMonth)}.`, tone:'neutral'});
  out.push({title:`Último mes visible: ${fmt(k.latestMonthTotal)}`, body:`${monthLabel(k.latestMonth)} · ${pct(k.latestDeltaPct)} vs mes anterior visible. Categoría dominante: ${latestCat}.`, tone:(k.latestDeltaPct||0)>10?'warn':(k.latestDeltaPct||0)<-10?'good':'neutral'});
  if(v.categories[0]) out.push({title:`Mayor bolsa: ${v.categories[0].name}`, body:`Representa ${v.categories[0].share.toFixed(1)}% del gasto filtrado (${fmt(v.categories[0].total)}).`, tone:'neutral'});
  if(v.concepts[0]) out.push({title:`Concepto dominante: ${v.concepts[0].name}`, body:`Suma ${fmt(v.concepts[0].total)} en ${v.concepts[0].count} líneas de factura.`, tone:'neutral'});
  return out;
}
function noData(id,msg='Sin datos con estos filtros'){el(id).innerHTML=`<div class="statusline" style="padding:28px">${msg}</div>`}


function schoolYearKey(month){
  if(!month) return '';
  const [y,m]=month.split('-').map(Number);
  const start=m>=9?y:y-1;
  return `${start}-${String(start+1).slice(-2)}`;
}
function courseMonthIndex(month){
  if(!month) return 0;
  const m=Number(month.slice(5,7));
  return m>=9 ? m-8 : m+4;
}
function safePct(part,total){return total ? part/total*100 : 0}
function lineRows(invs){
  const out=[];
  invs.forEach(inv=>scopedLines(inv).forEach(l=>out.push({invoice:inv, ...l})));
  return out;
}
function financeSnapshot(v){
  const rows=lineRows(v.invoices), months=v.months.map(m=>m.month).sort(), latest=months.at(-1)||'';
  const conceptMonths={};
  rows.forEach(r=>{(conceptMonths[r.nombre] ||= new Set()).add(r.invoice.mes)});
  let recurring=0, punctual=0;
  rows.forEach(r=>{(conceptMonths[r.nombre]?.size||0)>=6 ? recurring+=r.importeNumero : punctual+=r.importeNumero});
  const deltas=[];
  for(let i=1;i<v.months.length;i++){
    const prev=v.months[i-1], cur=v.months[i];
    if(prev.total) deltas.push({month:cur.month, prev:prev.month, delta:cur.total-prev.total, pct:(cur.total-prev.total)/prev.total*100});
  }
  const meaningful=deltas.filter(d=>Math.abs(d.delta)>120 && Math.abs(d.pct)>20).sort((a,b)=>Math.abs(b.delta)-Math.abs(a.delta));
  const currentCourse=schoolYearKey(latest), courseInvoices=v.invoices.filter(i=>schoolYearKey(i.mes)===currentCourse);
  const courseMonths=uniq(courseInvoices.map(i=>i.mes)).sort();
  const courseSpent=sum(courseInvoices,effectiveAmount), elapsed=Math.max(1, Math.min(10, courseMonths.filter(m=>courseMonthIndex(m)<=10).length));
  const forecast=courseSpent/elapsed*10;
  const courses={};
  DATA.invoices.forEach(inv=>{const key=schoolYearKey(inv.mes); if(key) courses[key]=(courses[key]||0)+inv.importe});
  const completed=Object.entries(courses).filter(([k])=>k!==currentCourse).sort();
  const reference=completed.at(-1)?.[1] || 0;
  const other=v.categories.find(c=>c.name==='Otros')?.total||0;
  const noLines=v.invoices.filter(i=>!i.lines?.length).length;
  const refunds=rows.filter(r=>r.importeNumero<0).length;
  return {rows, months, latest, recurring, punctual, deltas:meaningful, currentCourse, courseSpent, elapsed, forecast, reference, other, noLines, refunds};
}
function mini(id, items){
  el(id).innerHTML = items.length ? items.map(it=>`<div class="mini-item ${it.tone||''}"><strong>${it.title}</strong><div class="statusline">${it.body}</div>${it.meter!=null?`<div class="meter"><span style="width:${Math.max(0,Math.min(100,it.meter))}%"></span></div>`:''}</div>`).join('') : '<div class="statusline">Sin señales relevantes con estos filtros.</div>';
}
function renderExecutiveSummary(v){
  if(!v.invoices.length) return mini('executiveSummary', []);
  const f=financeSnapshot(v), top=v.categories[0], latest=v.kpis.latestMonthTotal, avg=v.kpis.avgMonth;
  const items=[
    {title:`Total filtrado: ${fmt(v.total)}`, body:`${v.kpis.invoiceCount} facturas en ${v.kpis.monthCount} meses. Media mensual: ${fmt(avg)}.`},
    {title:`Último mes visible: ${fmt(latest)}`, body:`${monthLabel(v.kpis.latestMonth)} · ${pct(v.kpis.latestDeltaPct)} frente al mes anterior visible.`, tone:(v.kpis.latestDeltaPct||0)>20?'warn':''},
    {title:`Mayor foco de gasto: ${top?.name||'—'}`, body:`${fmt(top?.total||0)} · ${safePct(top?.total||0,v.total).toFixed(1)}% del total filtrado.`}
  ];
  mini('executiveSummary', items);
}
function cleanChartText(option){
  const font='Inter, ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif';
  const clean={fontFamily:font, color:'#c7d4f2', textBorderWidth:0, textShadowBlur:0};
  const apply=o=>{ if(o && typeof o==='object') Object.assign(o, clean); };
  apply(option.textStyle ||= {});
  ['xAxis','yAxis'].forEach(axis=>{
    const axes=Array.isArray(option[axis])?option[axis]:[option[axis]].filter(Boolean);
    axes.forEach(a=>{apply(a.axisLabel ||= {}); apply(a.nameTextStyle ||= {})});
  });
  const series=Array.isArray(option.series)?option.series:[option.series].filter(Boolean);
  series.forEach(s=>{apply(s.label ||= {}); if(s.emphasis) apply(s.emphasis.label ||= {})});
  if(option.legend) apply(option.legend.textStyle ||= {});
  return option;
}
function setExplainedChart(id, option){
  if(!window.echarts) return;
  const key='_'+id;
  if(window[key] && typeof window[key].dispose==='function') window[key].dispose();
  const chart=window[key]=echarts.init(el(id), null, {renderer:'svg'});
  chart.setOption(cleanChartText({backgroundColor:'transparent', textStyle:{color:'#c7d4f2'}, ...option}));
  window.addEventListener('resize', ()=>chart.resize(), {passive:true});
}
function explain(id, html){el(id).innerHTML=html || 'Sin señales relevantes con estos filtros.'}
function renderAnomalyPanel(v){
  const f=financeSnapshot(v);
  const rows=f.deltas.slice(0,6).reverse();
  if(!rows.length){ noData('anomalyChart','Sin anomalías relevantes'); return explain('anomalyPanel','No hay meses con cambios fuertes bajo los filtros actuales.'); }
  setExplainedChart('anomalyChart', {
    grid:{left:88,right:22,top:18,bottom:24},
    tooltip:{trigger:'axis', formatter:ps=>ps.map(p=>`${p.name}: <b>${fmt(Math.abs(p.value))}</b> (${p.value>0?'subida':'bajada'})`).join('<br>')},
    xAxis:{type:'value', axisLabel:{formatter:v=>fmt(Math.abs(v)).replace(',00 €','')}, splitLine:{lineStyle:{color:'rgba(255,255,255,.08)'}}},
    yAxis:{type:'category', data:rows.map(d=>monthLabel(d.month)), axisLine:{show:false}, axisTick:{show:false}},
    series:[{type:'bar', data:rows.map(d=>({value:d.delta,itemStyle:{color:d.delta>0?'#ffb020':'#45d483'}})), label:{show:true, position:'right', formatter:p=>fmt(Math.abs(p.value)).replace(',00 €','')}}]
  });
  const main=rows.at(-1);
  explain('anomalyPanel', `<strong>Qué muestra:</strong> los meses donde el gasto se separa más de su mes anterior.<br><strong>Lectura:</strong> ${monthLabel(main.month)} tuvo ${main.delta>0?'una subida':'una bajada'} de ${fmt(Math.abs(main.delta))} (${pct(main.pct)}). Sirve para detectar excursiones, libros, regularizaciones o cargos raros sin revisar factura a factura.`);
}
function renderRecurringPanel(v){
  const f=financeSnapshot(v), total=f.recurring+f.punctual;
  setExplainedChart('recurringChart', {
    tooltip:{trigger:'item', formatter:p=>`${p.name}<br><b>${fmt(p.value)}</b> · ${p.percent}%`},
    legend:{bottom:0,textStyle:{color:'#c7d4f2'}},
    series:[{type:'pie', radius:['48%','72%'], center:['50%','44%'], avoidLabelOverlap:true, data:[{name:'Recurrente',value:f.recurring,itemStyle:{color:'#18c7a7'}},{name:'Puntual',value:f.punctual,itemStyle:{color:'#ffb020'}}]}]
  });
  explain('recurringPanel', `<strong>Qué muestra:</strong> separa conceptos que aparecen en 6+ meses de gastos menos repetidos.<br><strong>Lectura:</strong> el recurrente pesa ${safePct(f.recurring,total).toFixed(1)}% (${fmt(f.recurring)}). Es tu “coste base”; lo puntual (${fmt(f.punctual)}) explica los sustos y meses raros.`);
}
function renderForecastPanel(v){
  const f=financeSnapshot(v);
  const diff=f.reference ? f.forecast-f.reference : 0;
  setExplainedChart('forecastChart', {
    grid:{left:20,right:20,top:28,bottom:46,containLabel:true},
    tooltip:{trigger:'axis', axisPointer:{type:'shadow'}, formatter:ps=>ps.map(p=>`${p.name}: <b>${fmt(p.value)}</b>`).join('<br>')},
    xAxis:{type:'category', data:['Gastado','Proyección','Referencia'], axisLabel:{color:'#c7d4f2'}},
    yAxis:{type:'value', axisLabel:{formatter:v=>fmt(v).replace(',00 €','')}, splitLine:{lineStyle:{color:'rgba(255,255,255,.08)'}}},
    series:[{type:'bar', data:[{value:f.courseSpent,itemStyle:{color:'#4dabf7'}},{value:f.forecast,itemStyle:{color:diff>300?'#ffb020':'#18c7a7'}},{value:f.reference,itemStyle:{color:'#7c5cff'}}], label:{show:true, position:'top', formatter:p=>fmt(p.value).replace(',00 €','')}}]
  });
  explain('forecastPanel', `<strong>Qué muestra:</strong> extrapola el curso ${f.currentCourse||'actual'} a 10 meses lectivos y lo compara con el último curso comparable.<br><strong>Lectura:</strong> vas por ${fmt(f.courseSpent)} y la proyección es ${fmt(f.forecast)}${f.reference?`, ${diff>=0?'por encima':'por debajo'} de la referencia en ${fmt(Math.abs(diff))}`:''}.`);
}
function renderQualityPanel(v){
  const f=financeSnapshot(v), otherShare=safePct(f.other, v.total), noLineShare=safePct(f.noLines, v.invoices.length), refundShare=safePct(f.refunds, Math.max(1,f.rows.length));
  const data=[{name:'Otros',value:otherShare,color:otherShare>12?'#ffb020':'#18c7a7'},{name:'Sin líneas',value:noLineShare,color:f.noLines?'#ffb020':'#18c7a7'},{name:'Líneas negativas',value:refundShare,color:'#4dabf7'}];
  setExplainedChart('qualityChart', {
    grid:{left:110,right:28,top:18,bottom:24},
    tooltip:{trigger:'axis', formatter:ps=>ps.map(p=>`${p.name}: <b>${p.value.toFixed(1)}%</b>`).join('<br>')},
    xAxis:{type:'value', max:Math.max(20, ...data.map(d=>d.value))*1.15, axisLabel:{formatter:v=>`${v}%`}, splitLine:{lineStyle:{color:'rgba(255,255,255,.08)'}}},
    yAxis:{type:'category', data:data.map(d=>d.name), axisLine:{show:false}, axisTick:{show:false}},
    series:[{type:'bar', data:data.map(d=>({value:d.value,itemStyle:{color:d.color}})), label:{show:true, position:'right', formatter:p=>`${p.value.toFixed(1)}%`}}]
  });
  explain('qualityPanel', `<strong>Qué muestra:</strong> indicadores de fiabilidad del análisis.<br><strong>Lectura:</strong> “Otros” pesa ${otherShare.toFixed(1)}% (${fmt(f.other)}). Si sube, hay que mejorar reglas de categorización. Sin líneas: ${f.noLines}; líneas negativas: ${f.refunds}, normalmente abonos o regularizaciones.`);
}
function renderKpis(v){
  const k=v.kpis, avgInv=k.invoiceCount?k.total/k.invoiceCount:0, topChild=[...v.children].sort((a,b)=>b.total-a.total)[0];
  el('generated').textContent='Última generación: '+DATA.generatedAt.slice(0,19).replace('T',' ');
  el('kTotal').textContent=fmt(k.total); el('kTotalHint').textContent=`${k.invoiceCount} facturas · ${k.monthCount} meses filtrados`;
  el('kAvg').textContent=fmt(k.avgMonth); el('kMedian').textContent=`mediana ${fmt(k.medianMonth)}`;
  el('kLatest').textContent=fmt(k.latestMonthTotal); el('kLatestHint').innerHTML=`${monthLabel(k.latestMonth)} · <span class="delta ${deltaClass(k.latestDeltaPct)}">${pct(k.latestDeltaPct)}</span> vs mes anterior`;
  el('kMax').textContent=fmt(k.maxMonthTotal); el('kMaxHint').textContent=monthLabel(k.maxMonth);
  el('kTopCat').textContent=fmt(k.topCategoryTotal); el('kTopCatHint').textContent=k.topCategory;
  el('kChildren').innerHTML=v.children.length?v.children.map(c=>`<div>${c.name.split(' ')[0]}: <b>${fmt(c.total)}</b> <span class="hint">${c.share.toFixed(0)}%</span></div>`).join(''):'—';
  el('qWhere').textContent=k.topCategory; el('qWhere2').textContent=`${fmt(k.topCategoryTotal)} · ${k.total?(k.topCategoryTotal/k.total*100).toFixed(1):0}% del total filtrado`;
  el('qWatch').textContent=monthLabel(k.maxMonth); el('qWatch2').textContent=`máximo del periodo: ${fmt(k.maxMonthTotal)}`;
  el('qInvoice').textContent=fmt(avgInv);
  el('qChild').textContent=topChild?topChild.name.split(' ')[0]:'—'; el('qChild2').textContent=topChild?`${fmt(topChild.total)} · ${topChild.share.toFixed(1)}%`:'sin datos';
}
function renderInsights(v){}
function renderMoneyFlow(v){
  try {
    if(!v.invoices.length || !v.total) return noData('moneyFlowChart');
    if(!window.echarts){
      el('moneyFlowChart').innerHTML='<div class="statusline" style="padding:28px">No se ha podido cargar ECharts.</div>';
      return;
    }
    const shortFlowName = name => truncate(prettyConceptName(name).replace('Actividades complementarias','Act. complementarias').replace('Ampliación horaria','Ampliación').replace('Material / seguros','Material').replace('Salud / gabinete','Salud'), 28);
    const topCats=v.categories.filter(c=>c.total>0).slice(0,6);
    const restTotal=sum(v.categories.filter(c=>c.total>0).slice(6), c=>c.total);
    const cats=restTotal>1 ? [...topCats,{name:'Otros',total:restTotal,share:restTotal/v.total*100,other:true}] : topCats;
    const catNames=new Set(topCats.map(c=>c.name));
    const totalNode='__total__';
    const nodes=[{name:totalNode, labelName:`Total filtrado
${fmt(v.total)}`, depth:0, value:v.total, itemStyle:{color:'#18c7a7'}}];
    const links=[];
    const grouped=[];
    cats.forEach((cat,idx)=>{
      const catNode=`cat_${idx}`;
      nodes.push({name:catNode, labelName:`${shortFlowName(cat.name)}
${cat.share.toFixed(1)}%`, depth:1, value:cat.total, itemStyle:{color:colors[idx%colors.length]}});
      links.push({source:totalNode, target:catNode, value:Math.max(0.01,cat.total)});
      const concepts = (cat.other ? v.concepts.filter(c=>!catNames.has(c.category)) : v.concepts.filter(c=>c.category===cat.name)).filter(c=>c.total>0);
      grouped.push({catNode, idx, concepts});
    });
    grouped.forEach(({catNode,idx,concepts})=>{
      concepts.forEach((c,j)=>{
        const conceptNode=`cat_${idx}_concept_${j}`;
        nodes.push({name:conceptNode, labelName:`${shortFlowName(c.name)}
${fmt(c.total)}`, depth:2, value:c.total, itemStyle:{color:colors[idx%colors.length]}});
        links.push({source:catNode, target:conceptNode, value:Math.max(0.01,c.total)});
      });
    });
    if(window._moneyFlowChart && typeof window._moneyFlowChart.dispose === 'function') window._moneyFlowChart.dispose();
    const chart=window._moneyFlowChart=echarts.init(el('moneyFlowChart'), null, {renderer:'svg'});
    const labelByName=Object.fromEntries(nodes.map(n=>[n.name,n.labelName]));
    chart.setOption({
      backgroundColor:'transparent',
      tooltip:{trigger:'item', triggerOn:'mousemove', formatter:p=>{
        if(p.dataType==='edge') return `${labelByName[p.data.source]||p.data.source} → ${labelByName[p.data.target]||p.data.target}`.replaceAll('\\n',' ') + `<br><b>${fmt(p.data.value)}</b>`;
        return `${p.data.labelName||p.name}`.replaceAll('\\n','<br>') + `<br><b>${fmt(p.data.value||0)}</b>`;
      }},
      series:[{
        type:'sankey',
        left:20, right:230, top:28, bottom:28,
        nodeWidth:22, nodeGap:22, nodeAlign:'justify', layoutIterations:0,
        draggable:false,
        emphasis:{focus:'adjacency'},
        label:{color:'#eef4ff', fontSize:12, lineHeight:15, formatter:p=>p.data.labelName || p.name, overflow:'break', width:185},
        levels:[
          {depth:0, label:{position:'right', width:160, fontWeight:800}},
          {depth:1, label:{position:'right', width:170}},
          {depth:2, label:{position:'right', width:205, fontSize:11}}
        ],
        lineStyle:{color:'gradient', opacity:.32, curveness:.5},
        itemStyle:{borderWidth:0, borderRadius:5},
        data:nodes,
        links
      }]
    });
    window.addEventListener('resize', ()=>chart.resize(), {passive:true});
  } catch (err) {
    console.error('Error renderizando Sankey', err);
    el('moneyFlowChart').innerHTML='<div class="statusline" style="padding:28px">No he podido renderizar el gráfico de flujo con estos datos, pero el resto del dashboard sigue disponible.</div>';
  }
}
function renderMonthly(v){
  const w=900,h=370,pLeft=48,pTop=42,pBottom=86,data=v.months;if(!data.length)return noData('monthlyChart');
  const plotH=h-pTop-pBottom, max=Math.max(...data.map(d=>d.total))*1.12||1,gap=(w-pLeft*2)/data.length,bw=gap*.72;
  let grid=''; for(let i=0;i<=4;i++){const y=pTop+plotH*i/4; grid+=`<line x1="${pLeft}" y1="${y}" x2="${w-pLeft}" y2="${y}" stroke="#263655"/><text x="8" y="${y+4}" fill="#95a5c7" font-size="12">${fmt(max*(1-i/4)).replace(',00 €','€')}</text>`}
  const selected=el('monthFilter').value;
  const bars=data.map((d,i)=>{const x=pLeft+i*gap+gap*.14,bh=plotH*d.total/max,y=pTop+plotH-bh,active=selected===d.month; return `<rect x="${x}" y="${y}" width="${bw}" height="${bh}" rx="7" fill="url(#bar)" stroke="${active?'#eef4ff':'transparent'}" stroke-width="${active?3:0}" style="cursor:pointer" onclick="toggleMonthFilter('${d.month}')">${title(d.month,d.total)}</rect><text transform="translate(${x+bw/2},${h-34}) rotate(-35)" fill="${active?'#eef4ff':'#95a5c7'}" font-size="11" text-anchor="end" style="pointer-events:none">${monthLabel(d.month)}</text>`}).join('');
  el('monthlyChart').innerHTML=svg(w,h,`<defs><linearGradient id="bar" x1="0" y1="0" x2="0" y2="1"><stop stop-color="#18c7a7"/><stop offset="1" stop-color="#7c5cff"/></linearGradient></defs>${grid}${bars}`)
}
function renderDonut(v){
  const data=v.categories,total=sum(data,d=>d.total); if(!data.length||!total)return noData('donutChart');
  el('donutChart').innerHTML='<div class="donut-box"><div id="donutPie" style="width:100%;height:100%;min-height:340px"></div></div>';
  if(window._donutChart && typeof window._donutChart.dispose==='function') window._donutChart.dispose();
  const chart=window._donutChart=echarts.init(el('donutPie'), null, {renderer:'svg'});
  chart.setOption({
    backgroundColor:'transparent',
    tooltip:{trigger:'item', formatter:p=>`${p.name}<br><b>${fmt(p.value)}</b> · ${p.percent}%`},
    series:[{
      type:'pie',
      radius:['42%','72%'],
      center:['50%','50%'],
      avoidLabelOverlap:true,
      minShowLabelAngle:0,
      itemStyle:{borderColor:'#111a2e', borderWidth:3},
      label:{
        show:true,
        position:'outside',
        color:'#eef4ff',
        fontSize:12,
        lineHeight:15,
        formatter:p=>`${p.name}\n${fmt(p.value)} · ${p.percent}%`
      },
      labelLine:{
        show:true,
        length:18,
        length2:16,
        smooth:true,
        lineStyle:{color:'#95a5c7', width:1.2}
      },
      emphasis:{scale:true, scaleSize:7},
      data:data.map((d,i)=>({name:d.name, value:d.total, itemStyle:{color:colors[i%colors.length]}}))
    }]
  });
  chart.on('click', p=>toggleCategoryFilter(p?.name));
  window.addEventListener('resize', ()=>chart.resize(), {passive:true});
}
function prettyConceptName(name){
  return name.replace(/^E\.M\.\s*/,'').replace(/^C\.D\.\s*/,'').replace(/^A\.C\.\s*/,'').replace(/^A\.C\.R\.\s*/,'').replace(/^C\.D\.R\.\s*/,'').replace(/^E\.M\.R\.\s*/,'').replace(/REGULARIZACIÓN/g,'regularización').replace(/KÁRATE/g,'Karate').replace(/NATACIÓN/g,'Natación').replace(/ROBÓTICA/g,'Robótica').replace(/AMPLIACIÓN MAÑANA/g,'Ampliación mañana').replace(/COMEDOR/g,'Comedor').replace(/ALOHA MENTAL ARITHMETIC/g,'Aloha').replace(/PIANO/g,'Piano').replace(/AJEDREZ/g,'Ajedrez');
}
function activityPrices(invs){
  const map={};
  invs.forEach(inv=>scopedLines(inv).forEach(l=>{
    if(Math.abs(l.importeNumero)<1) return;
    const n=l.nombre;
    if(/MATRICULACI|REGULARIZACI|DESCUENTO|SEGURO|MATERIAL|FOTOGRAF|LIBROS|ENV[IÍ]O/i.test(n)) return;
    const key=n.replace(/\s+/g,' ').trim();
    (map[key] ||= {name:key, amounts:[], total:0, children:new Set(), months:new Set()});
    map[key].amounts.push(l.importeNumero); map[key].total+=l.importeNumero; map[key].children.add(inv.childName); map[key].months.add(inv.mes);
  }));
  return Object.values(map).map(x=>{
    const counts={}; x.amounts.forEach(a=>{const k=a.toFixed(2); counts[k]=(counts[k]||0)+1});
    const [habitual,count]=Object.entries(counts).sort((a,b)=>b[1]-a[1] || Math.abs(Number(b[0]))-Math.abs(Number(a[0])))[0] || [0,0];
    const positives=x.amounts.filter(a=>a>0).sort((a,b)=>a-b);
    const avg=positives.length?sum(positives)/positives.length:0;
    const latest=[...x.months].sort().at(-1);
    return {...x, display:prettyConceptName(x.name), habitual:Number(habitual), habitualCount:count, avg, months:x.months.size, children:[...x.children].join(', '), latest};
  }).filter(x=>x.months>=1).sort((a,b)=>Math.abs(b.total)-Math.abs(a.total));
}
function renderPrices(v){
  const data=activityPrices(v.invoices).slice(0,16);
  if(!data.length){el('priceCards').innerHTML='<div class="statusline">Sin conceptos de actividad con estos filtros.</div>'; return;}
  el('priceCards').innerHTML=data.map(x=>`<div class="price-card"><div class="name">${x.display}</div><div class="amount">${fmt(x.habitual)}</div><div class="meta">cuota habitual (${x.habitualCount} veces) · media ${fmt(x.avg)}</div><div class="meta">${x.children} · ${x.months} meses · último ${monthLabel(x.latest)}</div></div>`).join('');
}
function renderConcepts(v){
  const data=v.concepts.slice(0,12),w=900,h=330,p=10;if(!data.length)return noData('conceptChart'); const max=Math.max(...data.map(d=>d.total))||1,row=(h-p*2)/data.length;
  const items=data.map((d,i)=>{const y=p+i*row+4,bw=(w-310)*d.total/max;return `<text x="12" y="${y+18}" fill="#dbe6ff" font-size="13">${truncate(prettyConceptName(d.name),36)}</text><rect x="305" y="${y}" width="${bw}" height="${row-9}" rx="8" fill="${colors[i%colors.length]}">${title(d.name,d.total)}</rect><text x="${Math.min(305+bw+8,w-95)}" y="${y+18}" fill="#c7d4f2" font-size="12">${fmt(d.total)}</text>`}).join('');
  el('conceptChart').innerHTML=svg(w,h,items)
}
function renderHeat(v){
  const data=[...v.months].sort((a,b)=>b.total-a.total).slice(0,10); if(!data.length)return noData('heatChart'); const max=Math.max(...data.map(d=>d.total))||1;
  el('heatChart').innerHTML=`<div class="heat">${data.map(d=>`<div class="heat-row"><b>${monthLabel(d.month)}</b><div class="heat-bar"><div class="heat-fill" style="width:${d.total/max*100}%"></div></div><span class="num">${fmt(d.total)}</span></div>`).join('')}</div>`
}
function renderChildren(v){
  const names=uniq(DATA.invoices.map(i=>i.childName)),w=900,h=370,pLeft=48,pTop=42,pBottom=86,months=v.months;if(!months.length)return noData('childrenChart'); const plotH=h-pTop-pBottom,max=Math.max(...months.map(m=>Object.values(m.children).reduce((a,b)=>a+b,0)))*1.1||1,gap=(w-pLeft*2)/months.length,bw=gap*.72;
  const bars=months.map((m,i)=>{let y=pTop+plotH,parts=''; names.forEach((c,ci)=>{const val=m.children[c]||0,bh=plotH*val/max;y-=bh;if(val)parts+=`<rect x="${pLeft+i*gap+gap*.14}" y="${y}" width="${bw}" height="${bh}" fill="${colors[ci]}">${title(m.month+' · '+c,val)}</rect>`});return parts+`<text transform="translate(${pLeft+i*gap+gap*.5},${h-34}) rotate(-35)" fill="#95a5c7" font-size="11" text-anchor="end">${monthLabel(m.month)}</text>`}).join('');
  const legend=names.map((n,i)=>`<span class="concept" style="display:inline-flex;margin-right:14px"><span class="dot" style="background:${colors[i]}"></span>${n}</span>`).join('');
  el('childrenChart').innerHTML=legend+svg(w,h,bars)
}
function schoolYearStart(dateIso){const y=Number(dateIso.slice(0,4)), m=Number(dateIso.slice(5,7)); return m>=9?y:y-1}
function renderYears(v){
  const labels=['Sep','Oct','Nov','Dic','Ene','Feb','Mar','Abr','May','Jun','Jul','Ago'];
  const selectedStart=schoolYearStart(el('dateFrom').value || schoolYearDefaults().dateFrom);
  const base=baseFilteredInvoices({ignoreDate:true});
  const monthKey=(start,idx)=>{const month=((8+idx)%12)+1; const year=start+(idx>=4?1:0); return `${year}-${String(month).padStart(2,'0')}`};
  const totalFor=m=>sum(base.filter(inv=>inv.mes===m), effectiveAmount);
  const current=labels.map((label,i)=>({label,month:monthKey(selectedStart,i),total:totalFor(monthKey(selectedStart,i))}));
  const previous=labels.map((label,i)=>({label,month:monthKey(selectedStart-1,i),total:totalFor(monthKey(selectedStart-1,i))}));
  const w=900,h=330,p=45,max=Math.max(1,...current.map(d=>d.total),...previous.map(d=>d.total))*1.15,gap=(w-p*2)/12,bw=gap*.32;
  const bars=labels.map((lab,i)=>{const x=p+i*gap+gap*.18, ph=(h-p*2)*previous[i].total/max, ch=(h-p*2)*current[i].total/max, py=h-p-ph, cy=h-p-ch; return `<rect x="${x}" y="${py}" width="${bw}" height="${ph}" rx="5" fill="#4dabf7">${title(previous[i].month,previous[i].total)}</rect><rect x="${x+bw+4}" y="${cy}" width="${bw}" height="${ch}" rx="5" fill="#18c7a7">${title(current[i].month,current[i].total)}</rect><text x="${x+bw}" y="${h-14}" fill="#95a5c7" font-size="12" text-anchor="middle">${lab}</text>`}).join('');
  const currentTotal=sum(current,d=>d.total), previousTotal=sum(previous,d=>d.total), delta=previousTotal?((currentTotal-previousTotal)/previousTotal*100):null;
  const legend=`<div class="statusline" style="margin-bottom:8px"><span class="dot" style="background:#18c7a7"></span> Curso ${selectedStart}/${String(selectedStart+1).slice(2)}: <b>${fmt(currentTotal)}</b> · <span class="dot" style="background:#4dabf7;margin-left:12px"></span> Curso ${selectedStart-1}/${String(selectedStart).slice(2)}: <b>${fmt(previousTotal)}</b> · diferencia <span class="delta ${deltaClass(delta)}">${pct(delta)}</span></div>`;
  el('yearChart').innerHTML=legend+svg(w,h,bars)
}
function renderCurrentMonth(v){
  const now=new Date(), current=`${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,'0')}`;
  const invs=v.invoices.filter(i=>i.mes===current), total=sum(invs,effectiveAmount), hasCatFilter=selectedCategories().length;
  el('currentMonthStatus').textContent=`${monthLabel(current)} · ${invs.length} recibos · ${fmt(total)}`;
  const rows=invs.map(inv=>{const lines=hasCatFilter?scopedLines(inv):inv.lines;return `<tr><td>${inv.fechaIso}</td><td><b>${inv.factura}</b></td><td>${inv.childName}</td><td>${lines.slice(0,3).map(l=>l.nombre).join('<br>')}${lines.length>3?'<br>…':''}</td><td class="num"><b>${fmt(effectiveAmount(inv))}</b></td><td>${inv.pdf?`<a href="${inv.pdf}">PDF</a>`:''}</td></tr>`}).join('');
  el('currentMonthTable').querySelector('tbody').innerHTML=rows || '<tr><td colspan="6">No hay recibos del mes actual con estos filtros.</td></tr>'
}
function renderCategoryFilter(){
  const cats=selectedCategories();
  el('categoryButtonText').textContent=categoryLabel();
  el('categoryButton').classList.toggle('active', !!cats.length);
  el('categoryOptions').querySelectorAll('input[type=checkbox]').forEach(input=>{input.checked=cats.includes(input.value)});
}
function setupCategoryFilter(cats){
  el('categoryOptions').innerHTML=cats.map((c,i)=>`<label class="multi-option"><input type="checkbox" value="${c}"><span class="swatch" style="background:${colors[i%colors.length]}"></span><span>${c}</span></label>`).join('');
  el('categoryButton').addEventListener('click',e=>{e.stopPropagation();el('categoryFilter').classList.toggle('open')});
  el('categoryOptions').addEventListener('change',e=>{if(e.target.matches('input[type=checkbox]')) toggleCategoryChoice(e.target.value)});
  el('selectAllCategories').onclick=()=>{setSelectedCategories(cats);persistDraft();renderAll()};
  el('clearCategories').onclick=()=>{setSelectedCategories([]);persistDraft();renderAll()};
  document.addEventListener('click',e=>{if(!el('categoryFilter').contains(e.target)) el('categoryFilter').classList.remove('open')});
}
function setupFilters(){
  const cats=DATA.categories.map(c=>c.name),months=DATA.months.map(m=>m.month).reverse(),children=DATA.children.map(c=>c.name);
  setupCategoryFilter(cats);
  el('childFilter').innerHTML += children.map(c=>`<option>${c}</option>`).join('');
  el('monthFilter').innerHTML += months.map(m=>`<option value="${m}">${monthLabel(m)}</option>`).join('');
  const defaults=schoolYearDefaults(); el('dateFrom').value=defaults.dateFrom; el('dateTo').value=defaults.dateTo;
  ['search','dateFrom','dateTo','childFilter','monthFilter'].forEach(id=>el(id).addEventListener('input',()=>{persistDraft();renderAll()}));
  el('currentSchoolYear').onclick=()=>{clearNonDateFilters();const d=schoolYearDefaults();el('dateFrom').value=d.dateFrom;el('dateTo').value=d.dateTo;persistDraft();renderAll()};
  el('allDates').onclick=()=>{clearNonDateFilters();el('dateFrom').value='';el('dateTo').value='';persistDraft();renderAll()};
  el('resetView').onclick=()=>{clearNonDateFilters();const d=schoolYearDefaults();el('dateFrom').value=d.dateFrom;el('dateTo').value=d.dateTo;persistDraft();renderAll()};
  el('saveView').onclick=()=>{localStorage.setItem('alexia-dashboard-view', JSON.stringify(currentFilters())); alert('Vista guardada en este navegador')};
  el('exportCsv').onclick=exportCsv;
  el('toggleKpis').onclick=()=>{
    const box=el('kpiSection'), open=box.style.display==='none';
    box.style.display=open?'block':'none';
    el('toggleKpis').textContent=open?'Ocultar':'Mostrar';
  };
  el('togglePrices').onclick=()=>{
    const box=el('priceSection'), open=box.style.display==='none';
    box.style.display=open?'block':'none';
    el('togglePrices').textContent=open?'Ocultar':'Mostrar';
  };
  el('toggleComparatives').onclick=()=>{
    const box=el('comparativesSection'), open=box.style.display==='none';
    box.style.display=open?'block':'none';
    el('toggleComparatives').textContent=open?'Ocultar':'Mostrar';
  };
  el('toggleAnalysis').onclick=()=>{
    const box=el('analysisSection'), open=box.style.display==='none';
    box.style.display=open?'block':'none';
    el('toggleAnalysis').textContent=open?'Ocultar':'Mostrar';
    if(open){
      ['_anomalyChart','_forecastChart','_recurringChart','_qualityChart'].forEach(k=>window[k]?.resize?.());
    }
  };
}
function renderTable(v){
  const hasCatFilter=selectedCategories().length, invs=v.invoices, total=v.total, rows=[];
  invs.forEach((inv,idx)=>{const lines=hasCatFilter?scopedLines(inv):inv.lines;rows.push(`<tr class="invoice-row" onclick="document.getElementById('d${idx}').classList.toggle('open')"><td>${inv.fechaIso}</td><td><b>${inv.factura}</b><br><span class="pill">${inv.estado}</span></td><td>${inv.childName}</td><td>${lines.slice(0,3).map(l=>l.nombre).join('<br>')}${lines.length>3?'<br>…':''}</td><td>${inv.beneficiario}</td><td class="num"><b>${fmt(effectiveAmount(inv))}</b></td><td>${inv.pdf?`<a href="${inv.pdf}">PDF</a>`:''}</td></tr>`);rows.push(`<tr id="d${idx}" class="details"><td colspan="7"><ul>${lines.map(l=>`<li><span class="pill">${l.categoria}</span> ${l.nombre} — ${l.unidades} × ${l.importeUnitario} = <b>${l.importeTotal}</b></li>`).join('')}</ul></td></tr>`)});
  el('tableStatus').textContent=`${invs.length} facturas · ${fmt(total)} en la vista actual · ${el('dateFrom').value || 'inicio'} → ${el('dateTo').value || 'fin'}`;
  el('invoiceTable').querySelector('tbody').innerHTML=rows.join('') || '<tr><td colspan="7">Sin resultados</td></tr>'
}
function exportCsv(){
  const invs=filteredInvoices();
  const rows=[['fecha','factura','nino','beneficiario','importe','conceptos']].concat(invs.map(i=>[i.fechaIso,i.factura,i.childName,i.beneficiario,i.importe,i.lines.map(l=>`${l.nombre} (${l.importeTotal})`).join(' | ')]));
  const csv=rows.map(r=>r.map(x=>'"'+String(x).replaceAll('"','""')+'"').join(',')).join('\n');
  const a=document.createElement('a'); a.href=URL.createObjectURL(new Blob([csv],{type:'text/csv;charset=utf-8'})); a.download='facturas-alexia-filtradas.csv'; a.click();
}
function renderAll(){const view=computeView(filteredInvoices()); renderCategoryFilter(); renderKpis(view);renderExecutiveSummary(view);renderAnomalyPanel(view);renderRecurringPanel(view);renderForecastPanel(view);renderQualityPanel(view);renderCurrentMonth(view);renderMoneyFlow(view);renderMonthly(view);renderDonut(view);renderPrices(view);renderConcepts(view);renderHeat(view);renderChildren(view);renderYears(view);renderTable(view); const cats=selectedCategories(), month=el('monthFilter').value; el('filterStatus').textContent=view.invoices.length?`Vista filtrada: ${el('dateFrom').value || 'inicio'} → ${el('dateTo').value || 'fin'}${month ? ' · mes: '+monthLabel(month) : ''} · ${view.invoices.length} facturas · ${fmt(view.total)} · ${cats.length ? 'categorías: '+cats.join(', ') : 'todas las categorías'}`:`Sin facturas con estos filtros. Pulsa “Curso actual” o “Todo” para recuperar la vista.`}
setupFilters();renderAll();</script>
</body>
</html>'''

(ROOT / 'index.html').write_text(html_template.replace('__PAYLOAD__', payload_json), encoding='utf-8')
print('Dashboard generado:', ROOT / 'index.html')
print('Facturas:', len(invoices), 'Total:', money(total), 'Meses:', len(months), 'Conceptos:', len(payload['concepts']))
print('Insights:', len(insights))

# Alexia

Automatizaciones de Alexia para comunicados y facturas del colegio.

Este repositorio publica el codigo del dashboard y de los generadores. Los datos reales de facturas, PDFs, estados locales, capturas, perfiles de navegador y credenciales quedan fuera del repositorio publico.

## Dashboard de facturas

- `dashboard/generate_dashboard.py`: genera el dashboard HTML local desde `facturas.json`.
- `dashboard/analyze_invoice_anomalies.py`: detecta cambios de importe frente al historico local.
- `dashboard/generate_invoice_summary.py`: genera resumen de facturas.
- `dashboard/vendor/echarts.min.js`: dependencia estatica usada por el dashboard.

Para regenerar el dashboard en la maquina local:

```bash
/home/flow/alexia-bot/run-alexia-facturas.sh
```

Para servirlo con login:

```bash
/home/flow/alexia-bot/start_dashboard.sh
```

El servidor usa SQLite local en `state/auth.sqlite3`, hashes de contraseña y enlaces de alta/restablecimiento enviados por email. Para crear o actualizar un usuario inicial:

```bash
python3 /home/flow/alexia-bot/dashboard_server.py init-user usuario@example.com 'contraseña'
```

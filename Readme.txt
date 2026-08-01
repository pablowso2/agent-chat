BotiBank
---------
Para realizar el despliegue es importante
python3 -m venv .
python -m pip install -r requirements.txt

PARA LANZARLO
-------------

Botibankserv - Backend
 Bal run main.bal

PARA ARRANCAR FRONTAL
uvicorn main:app --port 5000

Con AgentManager
SETEAR VARS:
export AMP_OTEL_ENDPOINT="https://opentelemetry.obs.dp.cloud.wso2.com/v1/traces"
export AMP_AGENT_API_KEY="eyJhbGciOiJSUzI1NiIsImtpZCI6ImtleS0xIiwidHlwIjoiSldUIn0.eyJpc3MiOiJhZ2VudC1tYW5hZ2VyLXNlcnZpY2UiLCJzdWIiOiJib3RpYmFuayIsImV4cCI6MTgxNTU1MDY1OSwibmJmIjoxNzg0MDE0NjU5LCJpYXQiOjE3ODQwMTQ2NTksImNvbXBvbmVudF91aWQiOiJmZDFjNDkzNi0wNmVhLTQwNzctOGIzMy03NzZiY2MzN2E0NzYiLCJlbnZpcm9ubWVudF91aWQiOiJlN2Q2ZTc1MS1hYmQ5LTQ4ZjItYmNlZS0xNDQ0OTRiMjJjY2YiLCJwcm9qZWN0X3VpZCI6IjRhOTViMDY5LTkxNmYtNDhjOS1iM2NmLWEyZjg3MjQ1OTgzMSIsIm9yZ19pZCI6IjAxOWU2MzgzLTYyOGYtNzc5MS04NmYwLTAyOTMwY2Y4ZTc5NSJ9.xZa5dmF9Q_kU2kAsCXKF1STAy6JBDueM5TG-97sUEvQXcQMWJ4l5pH8nWuDo3n5DOFJkJ_1Um2Vi0ESdbgFlJEpmAhAv2pWyq0h86tpSA_XClxCt9mO2WpkAraBH3SaxXThYBk6fuoXTwtS3ZDKfiiDq5ilB_sRrzwz-z8R-wqbyS_i2iCVyrogNHt56lTUtl0IRYF-IgotU0zQegPuNYKy25O84QgF5rKHKX-DgLqLZ-FFefdf3pZjVecoboD26V9qzVx8SeZwoY87H-dpe10mYfotPucwJBYk8JF9TFFf47hjgpUIqrnPDzT8MPAs3G7pszZ0C9d-04C9mtOtr6fM1DreEBa4axEA0q8AaZnv3zzl19mkZKr8suSU_quMMDXZmmUOuBzysj9M8H6jifi3JV_oHEbe91hzmKRVMFVzqg6MRxWSQaOgbAt7DzUaS95iPUwacSI2tNVoJ_uDJGOtHOLTehQIQ7Q_p7JYqfI7ZPJ44msBfrjQgIPlfvGMrBE6n1_6U96ToykF1DsEl3844Pz5oZg2OGIEsPg-0F-k7ICBBwI3_6QVzRx-us0SAh3RUN4f_pxl0KGQpt-pjXqUeYSXUywHTDpYFP8X6VVogcF8FPeYpLWxj6Vsq9bH-XChCSpHTMnCJjXzxGeYLG5p7rZKczPtsMocKQI9Owck"

amp-instrument python main.py   

Como obtener la lista de tools boti-bank tools
curl -k -X POST 'https://localhost:8243/botibankmcp/1.0/mcp' \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer TU_TOKEN_AQUI' \
  -d '{
    "jsonrpc": "2.0",
    "method": "tools/list",
    "id": 1
  }'

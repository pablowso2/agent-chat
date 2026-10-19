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
export AMP_AGENT_API_KEY="eyJhbGciOiJSUzI1NiIsImtpZCI6ImtleS0xIiwidHlwIjoiSldUIn0.eyJpc3MiOiJhZ2VudC1tYW5hZ2VyLXNlcnZpY2UiLCJzdWIiOiJib3RpYmFuayIsImV4cCI6MTc5NjEzMTExOCwibmJmIjoxNzg4MzU1MTE4LCJpYXQiOjE3ODgzNTUxMTgsImp0aSI6IjU4YjIwM2JmLWU3OWUtNGM0My04ODk2LTNlMTI4OTQyY2M3MiIsImNvbXBvbmVudF91aWQiOiJmZDFjNDkzNi0wNmVhLTQwNzctOGIzMy03NzZiY2MzN2E0NzYiLCJlbnZpcm9ubWVudF91aWQiOiJlN2Q2ZTc1MS1hYmQ5LTQ4ZjItYmNlZS0xNDQ0OTRiMjJjY2YiLCJwcm9qZWN0X3VpZCI6IjRhOTViMDY5LTkxNmYtNDhjOS1iM2NmLWEyZjg3MjQ1OTgzMSIsIm9yZ19pZCI6IjAxOWU2MzgzLTYyOGYtNzc5MS04NmYwLTAyOTMwY2Y4ZTc5NSIsIm5hbWVzcGFjZSI6IndjLTAxOWU2MzgzLWI2NWZhZDJiIn0.u5Wt4X2_Q25M6qDK3l-9J0tvhB3RysG8kJNXqPvMUVDbcPsB5G3D1hPWbi1IWBxaAa4zF2DFrAvkVHRlCOwI2Eu2n1krDEfLkHTgQ2QxoHKaCeGCxu9-IPbsMjNT8P7UsRXLvOi0ZLO2lpTQrZD8q-9dPWjW9ENCbbr_3bhLaaSvyZ7PEqrMgAppqkZXGI0nC85M9tMSFPDSakM-rTBij74qn38hN5Qyzny9Zj-2kmTSXMs2rvY42ivvVkxWsohbDZoVsCseiDxj7Xrz7yA90ThSZnyoo4fZawMLjPshNWC6Am-lKcSYHGyZHmpIouDadGNq2HLbaa7ocqaNaA28Om6HAhtEc6w-dk0rYe3oz7ClRjWPTTVLJeWC5iT8XHimyXv9ZqF7Gk-CRnt_xP1ahZboB4wKTcQeTXN34xGnI1m4zYL7sanRruKFrGaA6wyp5lxjihf1vqSOqq6F83PNibm1lG1U54XHZzuzQZvVqwmnWdziYgRSNY2J72pcImoRIE_Q_NicoxavTIYU7DjjdPsy6QeeZQOInWH1DUGEe67bgJlwit1WKMUM1EO1vHKuyeV5K09WVx95Qvw4v8W3LvbXtdukL9VV0P5wCs1AnczSkVDl0s03qf7Jhb-i8ZTE-bffrR2BMMCfWkeVvJID8sg88bRCWcIPoCj3ssGAH_s"

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


PARA PROBAR BOTI BANK LOCAL

1)Start the backend: bal run main.bal (/botibank/botibankserv)
2)Start the botibank-ext publicar eventos en agent manager amp-instrument python main.py (agent-chat/botibank)

3)PRobar los MCPs directos: ./test-botibank-mcp.sh 

4)Webhook moesif agent-chat/moesif (python main.py)
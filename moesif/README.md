Header Config

X-Moesif-Secret: secreto-moesif-123

curl -X POST http://127.0.0.1:1030/moesif-webhook \
  -H "Content-Type: application/json" \
  -H "X-Moesif-Secret: secreto-moesif-123" \
  -d '{
    "type": "alert",
    "name": "events_exceeded_threshold",
    "metric": "event count For Each response.status Condition is greater than 100 over the last day",
    "grouping_feature_level1": null,
    "grouping_feature_level2": null,
    "metric_values": [
      {
        "feature": "global",
        "value": 10.0,
        "direction": "spike"
      }
    ],
    "timestamp": "2023-07-05T06:16:54.953Z",
    "history": {
      "2023-07-05T06:16:50.953Z": [
        {
          "feature": "global",
          "value": 100
        }
      ],
      "2023-07-05T06:16:40.953Z": [
        {
          "feature": "global",
          "value": 120
        }
      ]
    }
  }'
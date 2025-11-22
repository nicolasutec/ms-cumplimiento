# StoreTaskToken.py
import os
import json
import boto3
from datetime import datetime, timezone

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(os.environ["ORDERS_TABLE"])


def lambda_handler(event, context):
    """
    Invocada por Step Functions con waitForTaskToken.

    event ejemplo:
    {
      "taskToken": "...",
      "step": "ASSIGN_COOK",
      "order": {
        "order_id": "abc-123",
        "tenant_id": "LIMA_CENTRO",
        ...
      }
    }
    """
    task_token = event["taskToken"]
    step = event["step"]
    order = event["order"]
    order_id = order["order_id"]

    now = datetime.now(timezone.utc).isoformat()

    table.update_item(
        Key={"order_id": order_id},
        UpdateExpression=(
            "SET pending_task_token = :token, "
            "pending_step = :step, "
            "pending_updated_at = :ts"
        ),
        ExpressionAttributeValues={
            ":token": task_token,
            ":step": step,
            ":ts": now,
        },
    )

    # Debe devolver rápido; Step Functions se queda esperando SendTaskSuccess
    return {"status": "OK", "order_id": order_id, "step": step}

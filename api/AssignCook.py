# api/AssignCook.py
import os
import json
import boto3
from datetime import datetime, timezone
from decimal import Decimal

dynamodb = boto3.resource("dynamodb")
stepfunctions = boto3.client("stepfunctions")

table = dynamodb.Table(os.environ["ORDERS_TABLE"])


def lambda_handler(event, context):
    order_id = event["pathParameters"]["order_id"]
    body = json.loads(event.get("body") or "{}")

    staff_id = body.get("staff_id")
    staff_name = body.get("staff_name")
    if not staff_id or not staff_name:
        return {"statusCode": 400, "body": json.dumps({"error": "staff_id y staff_name son requeridos"})}

    # Leer pedido
    res = table.get_item(Key={"order_id": order_id})
    item = res.get("Item")
    if not item:
        return {"statusCode": 404, "body": json.dumps({"error": "Order not found"})}

    if item.get("pending_step") != "ASSIGN_COOK":
        return {
            "statusCode": 409,
            "body": json.dumps({"error": "Order not waiting for cook assignment"}),
        }

    task_token = item.get("pending_task_token")
    if not task_token:
        return {
            "statusCode": 409,
            "body": json.dumps({"error": "No pending task token for this order"}),
        }

    now = datetime.now(timezone.utc).isoformat()

    # Enviar SendTaskSuccess a Step Functions
    output = {
        "order_id": order_id,
        "staff_id": staff_id,
        "staff_name": staff_name,
        "step": "ASSIGN_COOK",
        "timestamp": now,
    }

    stepfunctions.send_task_success(
        taskToken=task_token,
        output=json.dumps(output, default=str),
    )

    # Limpiar token pendiente en la tabla
    table.update_item(
        Key={"order_id": order_id},
        UpdateExpression="REMOVE pending_task_token, pending_step, pending_updated_at",
    )

    return {
        "statusCode": 200,
        "body": json.dumps({"message": "Cook assigned and workflow resumed", "order_id": order_id}),
    }

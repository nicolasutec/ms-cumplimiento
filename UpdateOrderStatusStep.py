# UpdateOrderStatusStep.py
import os
import json
import boto3
from datetime import datetime, timezone

dynamodb = boto3.resource("dynamodb")
eventbridge = boto3.client("events")

table = dynamodb.Table(os.environ["ORDERS_TABLE"])
EVENT_BUS_NAME = os.environ["EVENT_BUS_NAME"]

# Map interno de action -> status + evento
ACTION_CONFIG = {
    "INIT": {"status": "PENDIENTE", "event_type": "PedidoInicializado"},
    "COOKING": {"status": "COCINANDO", "event_type": "CocinaIniciada"},
    "PACKING": {"status": "EMPACANDO", "event_type": "EmpaqueIniciado"},
    "ON_DELIVERY": {"status": "EN_REPARTO", "event_type": "RepartoIniciado"},
    "DELIVERED": {"status": "ENTREGADO", "event_type": "PedidoEntregado"},
}


def lambda_handler(event, context):
    """
    Invocada por Step Functions.

    event:
    {
      "action": "COOKING" | "PACKING" | "ON_DELIVERY" | "DELIVERED" | "INIT",
      "payload": {
        "order_id": "...",
        ...
      }
    }
    """
    action = event["action"]
    payload = event["payload"]
    order_id = payload["order_id"]

    cfg = ACTION_CONFIG[action]
    new_status = cfg["status"]
    event_type = cfg["event_type"]

    now = datetime.now(timezone.utc).isoformat()

    # Agregamos entrada a historialPasos
    history_entry = {
        "action": action,
        "status": new_status,
        "timestamp": now,
    }

    table.update_item(
        Key={"order_id": order_id},
        UpdateExpression=(
            "SET #st = :st, "
            "updated_at = :ts "
            "ADD history :h"
        ),
        ExpressionAttributeNames={
            "#st": "status",
        },
        ExpressionAttributeValues={
            ":st": new_status,
            ":ts": now,
            ":h": {json.dumps(history_entry)},
        },
    )

    # Emitir evento a EventBridge para el servicio de Status/Dashboard
    eventbridge.put_events(
        Entries=[
            {
                "Source": "fulfillment.service",
                "DetailType": event_type,
                "Detail": json.dumps(
                    {
                        "order_id": order_id,
                        "status": new_status,
                        "timestamp": now,
                    }
                ),
                "EventBusName": EVENT_BUS_NAME,
            }
        ]
    )

    return {
        "order_id": order_id,
        "status": new_status,
        "ts": now,
    }

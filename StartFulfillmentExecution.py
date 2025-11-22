# StartFulfillmentExecution.py
import os
import json
import boto3
from datetime import datetime, timezone

stepfunctions = boto3.client("stepfunctions")
dynamodb = boto3.resource("dynamodb")

ORDERS_TABLE = os.environ["ORDERS_TABLE"]
STATE_MACHINE_ARN = os.environ["FULFILLMENT_STATE_MACHINE_ARN"]

table = dynamodb.Table(ORDERS_TABLE)


def lambda_handler(event, context):
    """
    EventBridge -> PedidoRecibido

    event["detail"] esperado:
    {
      "order_id": "abc-123",
      "tenant_id": "LIMA_CENTRO",
      "customer_id": "...",
      "total": 100.0,
      ...
    }
    """
    detail = event.get("detail", {})
    order_id = detail["order_id"]

    # Iniciar ejecución de Step Functions
    input_data = {
        "order_id": order_id,
        "tenant_id": detail.get("tenant_id"),
        "customer_id": detail.get("customer_id"),
        "total": detail.get("total"),
    }

    response = stepfunctions.start_execution(
        stateMachineArn=STATE_MACHINE_ARN,
        input=json.dumps(input_data),
        name=f"order-{order_id}-{int(datetime.now(timezone.utc).timestamp())}",
    )

    execution_arn = response["executionArn"]

    # Guardar el ARN de la ejecución en la tabla de pedidos
    table.update_item(
        Key={"order_id": order_id},
        UpdateExpression="SET step_function_arn = :arn",
        ExpressionAttributeValues={":arn": execution_arn},
    )

    return {
        "statusCode": 200,
        "body": json.dumps(
            {"message": "Fulfillment iniciado", "execution_arn": execution_arn}
        ),
    }

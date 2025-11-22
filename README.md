# Fulfillment Service (Order Workflow)

Microservicio serverless responsable de **orquestar el ciclo de vida de un pedido** una vez que ha sido creado por el _Order Service_.

Se encarga de:

- Escuchar el evento `PedidoRecibido` en **EventBridge**.  
- Iniciar una ejecución en **AWS Step Functions**.  
- Esperar acciones humanas del staff (cocinero, despachador, repartidor) mediante **endpoints HTTP**.  
- Actualizar el estado del pedido en **DynamoDB**.  
- Publicar eventos de cambios de estado hacia el **Servicio de Estado / Dashboard**.

---

## 🏗 Arquitectura General

### Componentes principales

- **EventBridge**
  - Recibe el evento `PedidoRecibido` desde el Order Service.
  - Dispara la Lambda `StartFulfillmentExecution`.

- **Step Functions**
  - Orquesta el flujo completo:
    ```
    PENDIENTE → COCINANDO → EMPACANDO → EN_REPARTO → ENTREGADO
    ```
  - Usa `waitForTaskToken` en los pasos donde interviene personal del restaurante.

- **Lambdas**
  - `StartFulfillmentExecution`: inicia Step Functions.
  - `StoreTaskToken`: guarda el `taskToken` y el paso pendiente.
  - `UpdateOrderStatusStep`: actualiza estado + historial + publica eventos.
  - Endpoints HTTP para el staff:
    - `AssignCook`
    - `MarkPacked`
    - `AssignDelivery`
    - `MarkDelivered`

- **DynamoDB**
  - Reutiliza la tabla `ORDERS_TABLE` (idealmente `ChinaWok_MainTable`).
  - Mantiene estado, historial, y `taskToken` necesarios para la orquestación.

---

## 🚨 Requisitos Previos

Antes de desplegar, debes asegurar:

### 1. Order Service activo  
- Debe crear pedidos en `ORDERS_TABLE`.
- Debe publicar `PedidoRecibido` en EventBridge con:
  - `source: "orders.service"`
  - `detail-type: "PedidoRecibido"`

### 2. EventBridge configurado
Debe existir un **Event Bus** con nombre `${EVENT_BUS_NAME}`.

### 3. Tabla DynamoDB existente
La tabla **no se crea aquí**; este servicio la asume ya creada.

### 4. Rol IAM con permisos
El rol `${ROLE_NAME}` debe tener:

- `dynamodb:GetItem`, `UpdateItem` sobre `${ORDERS_TABLE}`
- `states:StartExecution`, `states:SendTaskSuccess`
- `events:PutEvents` sobre `${EVENT_BUS_NAME}`

### 5. Plugins instalados

```bash
npm install --save-dev serverless-step-functions serverless-dotenv-plugin
```

---

## ⚙️ Variables de Entorno

Crear un archivo `.env` en la raíz:

```env
ORG_NAME=tu-org
FULFILLMENT_SERVICE_NAME=fulfillment-service
AWS_ACCOUNT_ID=123456789012
ROLE_NAME=FulfillmentRole

ORDERS_TABLE=ChinaWok_MainTable
EVENT_BUS_NAME=china-wok-bus
```

---

## 🗄 Modelo de Datos en DynamoDB

Independiente del diseño exacto (tabla simple o tabla única), el pedido debe contener:

- `order_id`
- `tenant_id`
- `status`
- `pending_task_token`
- `pending_step`
- `history` o `historialPasos`
- `step_function_arn`

Si usas **tabla única**, recuerda adaptar las Lambdas a:

```
PK = TENANT#{locationId}
SK = ORDER#{timestamp}
```

---

## 🔔 Evento de Entrada: PedidoRecibido

Ejemplo de evento que debe publicar el Order Service:

```json
{
  "Source": "orders.service",
  "DetailType": "PedidoRecibido",
  "Detail": "{ \"order_id\": \"abc-123\", \"tenant_id\": \"LIMA_CENTRO\", \"customer_id\": \"CLIENTE_999\", \"total\": 100.0 }",
  "EventBusName": "china-wok-bus"
}
```

---

## 🔄 Flujo de la State Machine

1. **InicializarPedido**  
   `status = PENDIENTE`

2. **EsperarAsignacionCocinero**  
   - Usa `waitForTaskToken`  
   - Guarda `pending_step = ASSIGN_COOK`

3. **Cocinando** (`COOKING`)

4. **EsperarEmpaque**  
   - `pending_step = PACK`

5. **Empacando** (`PACKING`)

6. **EsperarAsignacionRepartidor**  
   - `pending_step = ASSIGN_DELIVERY`

7. **EnReparto** (`ON_DELIVERY`)

8. **EsperarEntregado**  
   - `pending_step = MARK_DELIVERED`

9. **Entregado** (`DELIVERED`)

Cada transición:

- Actualiza estado en DynamoDB  
- Registra una entrada en `history`  
- Publica un evento (`CocinaIniciada`, `EmpaqueIniciado`, `RepartoIniciado`, `PedidoEntregado`, etc.) en EventBridge  

---

## 🧑‍🍳 API Endpoints (Uso Interno del Staff)

Cada endpoint es `POST` y requiere:

```json
{
  "staff_id": "STAFF#...",
  "staff_name": "Nombre"
}
```

### 1. Asignar cocinero  
**POST** `/orders/{order_id}/assign-cook`

Avanza el flujo desde `ASSIGN_COOK` → `COOKING`.

---

### 2. Marcar pedido como empacado  
**POST** `/orders/{order_id}/mark-packed`

Avanza desde `PACK` → `PACKING`.

---

### 3. Asignar repartidor  
**POST** `/orders/{order_id}/assign-delivery`

Avanza desde `ASSIGN_DELIVERY` → `ON_DELIVERY`.

---

### 4. Marcar entrega finalizada  
**POST** `/orders/{order_id}/mark-delivered`

Avanza desde `MARK_DELIVERED` → `DELIVERED`.

---

## 🚀 Despliegue

### 1. Instalar dependencias

```bash
npm install
```

### 2. Crear tu `.env`

```env
# Copiar el ejemplo anterior
```

### 3. Desplegar

```bash
sls deploy --stage dev
```

---

## 🧪 Flujo típico de uso (End-to-End)

1. Cliente crea pedido → Order Service lo guarda y dispara `PedidoRecibido`.
2. Fulfillment inicia ejecución de Step Functions.
3. Step Functions queda en `EsperarAsignacionCocinero`.
4. El dashboard llama a `/assign-cook`.
5. Step Functions avanza, registra estado y publica eventos.
6. Proceso continúa hasta `DELIVERED`.

---

## 🐞 Troubleshooting

| Problema | Causa probable | Solución |
|---------|----------------|----------|
| `409 Conflict` al llamar un endpoint | `pending_step` no coincide | Revisar en DynamoDB si el flujo está esperando otra acción |
| Step Functions no avanza | `SendTaskSuccess` no enviado | Revisar logs de la Lambda correspondiente |
| `StartFulfillmentExecution` no corre | Evento mal configurado | Validar EventBridge: bus correcto, source/detalle correctos |
| El pedido “se pierde” | No se guardó `pending_task_token` | Revisar Lambda `StoreTaskToken` |

---

## 📌 Notas finales

- Este microservicio NO crea la tabla de pedidos ni el event bus.  
- Es independiente del Order Service, lo cual garantiza desacoplamiento.  
- El flujo puede extenderse fácilmente añadiendo más pasos en la Step Function.  
- Todo el sistema está optimizado para escalar sin colisiones ni dependencias directas.  

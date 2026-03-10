## SYSTEM DESCRIPTION

Mars Habitat Automation Platform is a system designed to monitor and control a simulated Mars habitat through a unified automation platform.  
It ingests heterogeneous data streams produced by the Mars IoT Simulator, normalizes them into a standard event schema, and routes them to internal services.
Operators interact with the user interfaces to observe the current state of the habitat, configure automation behaviours, and ensure safety and stability

The core ideas of the system are:

- **Unified data model**: all sensor and actuator data are converted to a single internal event format to simplify processing by downstream services.
- **Event‑driven architecture**: normalized events are published to an internal broker, enabling decoupled services for monitoring, storage, rules evaluation, and actuation.
- **Automation rules engine**: operators can define, persist, and manage rules that react to sensor events and trigger actuator commands automatically.
- **Manual override**: operators can always directly interact with actuators, overriding or complementing automation when needed.

## USER STORIES

1. As an operator, I want to read sensors data, so that I can monitor the habitat
2. As an operator, I want to normalize sensors data, so that I can process them
3. As an operator, I want to create automation rules, so that I can automate the habitat
4. As an operator, I want to edit/delete existing automation rules, so that I can modify the behavior of the habitat
5. As an operator, I want to switch on/off automation rules, so that I can modify the behavior of the habitat
6. As an operator, I want to save automation rules, so that they persist after a restart
7. As an operator, I want to interact manually with actuators, so that I can directly control the habitat
8. As an operator, I want to see the latest sensor readings, so that I can react immediately to critical changes in the habitat
9. As an operator, I want to check sensors status, so that I can detect malfunctions
10. As an operator, I want to see the evolution of sensors data, so that I can understand the behavior of the habitat
11. As the software, I want to show conflicts between automator rules, so that the operator can solve the issue

# CONTAINERS:

## Ingestion-Service

Handles ingestion of raw sensor data from the simulator and publishes normalized events to the internal message broker.

### USER STORIES:

1. As an operator, I want to read sensors data, so that I can monitor the habitat
2. As an operator, I want to normalize sensors data, so that I can process them

### PORTS:

8000

### DESCRIPTION:

The Ingestion-Service container is responsible for polling or receiving data from the simulator and transforming heterogeneous payloads into the unified internal event schema (`UnifiedEvent`).  
Once normalized, the service publishes the events to RabbitMQ decoupling data producers from downstream consumers such as the Processor Service and monitoring components.

### PERSISTANCE EVALUATION

The Ingestion-Service container does not require persistent storage: it behaves as a stateless pipeline that pulls data from the simulator, normalizes it, and forwards it to RabbitMQ.  
In case of failure, the service can be restarted without losing critical state, since the simulator remains the source of truth for sensor data.

### EXTERNAL SERVICES CONNECTIONS

The Ingestion-Service container connects to:

- The **Mars IoT Simulator** via HTTP (REST) to poll sensor endpoints.
- The **RabbitMQ** broker to publish normalized `UnifiedEvent` messages.

### MICROSERVICES:

#### MICROSERVICE: ingestion-service

- TYPE: backend
- DESCRIPTION: Normalizes sensor readings coming from the simulator and publishes them to RabbitMQ using the unified event schema.
- PORTS: 8000
- TECHNOLOGICAL SPECIFICATION:
  - Implemented in Python using FastAPI as the web framework.
  - Uses an HTTP client to poll simulator endpoints.
  - Uses a RabbitMQ client library to publish messages.
- SERVICE ARCHITECTURE: 
  - A `poller` component periodically calls the simulator REST API to fetch the latest sensor readings.
  - A `models` module defines the internal `UnifiedEvent` schema used for normalization.
  - A `rabbitmq` module encapsulates connection and publishing logic to the message broker.
- ENDPOINTS:

  | HTTP METHOD | URL     | Description                          | User Stories |
  | ----------- | ------- | ------------------------------------ |-------------|
  | GET         | /health | Returns health status of the service | -           |


## Processor-Service

Manages the in-memory state of sensors, evaluates automation rules, preserves them, and triggers actuator commands based on incoming events.

### USER STORIES:

1. As an operator, I want to read sensors data, so that I can monitor the habitat  
3. As an operator, I want to create automation rules, so that I can automate the habitat  
4. As an operator, I want to edit/delete existing automation rules, so that I can modify the behavior of the habitat  
5. As an operator, I want to switch on/off automation rules, so that I can modify the behavior of the habitat  
6. As an operator, I want to save automation rules, so that they persist after a restart  
8. As an operator, I want to see the latest sensor readings, so that I can react immediately to critical changes in the habitat  
9. As an operator, I want to check sensors status, so that I can detect malfunctions  
10. As an operator, I want to see the evolution of sensors data, so that I can understand the behavior of the habitat  
11. As the software, I want to show conflicts between automator rules, so that the operator can solve the issue  

### PORTS:

8002:8000

### DESCRIPTION:

The Processor-Service container listen to the normalized events from RabbitMQ, keeps an in-memory cache of the latest sensor readings, and evaluates IF–THEN automation rules and active conflicts between rules targeting the same actuator (set the actuator OFF when a conflict is generated).  
When rule conditions are met, it issues actuator commands back to the simulator, either directly or via the API Gateway.

### PERSISTANCE EVALUATION

The Processor-Service container requires persistent storage to keep automation rules across restarts.  
Rules are stored in a SQLite database mounted on a Docker volume, ensuring that configurations (conditions, actions, priorities, active flags) survive container recreation while the live sensor state remains in memory only.

### EXTERNAL SERVICES CONNECTIONS

The Processor-Service container connects to:
- The **RabbitMQ** broker to consume normalized `UnifiedEvent` messages and optionally publish derived events.  
- The **Mars IoT Simulator** via HTTP to send actuator commands when rules fire.  

### MICROSERVICES:

#### MICROSERVICE: processor-service

- TYPE: backend  
- DESCRIPTION: Consumes normalized events, maintains the sensor state cache, evaluates automation rules, persists them, and triggers actuator commands, also exposing APIs for rules and state.  
- PORTS: 8000  
- TECHNOLOGICAL SPECIFICATION:
  - Implemented in Python using FastAPI as the web framework.
  - Uses RabbitMQ client library to consume events from the broker.
  - Uses SQLite to keep automation rules.
  - Uses an async HTTP client to send actuator commands to the simulator.
- SERVICE ARCHITECTURE:
  - A **RabbitMQ consumer** listens to the normalized event stream and updates an in-memory **state cache** keyed by sensor/source.
  - A **rule engine** evaluates incoming events against active rules and decides which actuator actions to perform.
  - An **arbitrator** module detects and exposes conflicts between rules acting on the same actuator with opposite settings.
  - A **database layer** manages CRUD operations on rules stored in SQLite.
  - FastAPI **routes** expose health, state, conflicts and rules CRUD endpoints.

- ENDPOINTS:

    | HTTP METHOD | URL                   | Description                                                | User Stories      |
    |-------------|-----------------------|------------------------------------------------------------|-------------------|
    | GET         | /health               | Returns health status and number of cached sensors         | 1, 8, 9           |
    | GET         | /api/state            | Returns the full in-memory state of all sensors            | 1, 8, 9, 10       |
    | GET         | /api/state/{source}   | Returns the latest event for a specific sensor             | 1, 8, 9           |
    | GET         | /api/conflicts        | Returns currently active conflicts between automation rules| 11                |
    | GET         | /api/rules            | Lists all automation rules                                 | 3, 4, 5, 6        |
    | GET         | /api/rules/{rule_id}  | Returns a specific automation rule                         | 3, 4, 5, 6        |
    | POST        | /api/rules            | Creates a new automation rule                              | 3, 6              |
    | PUT         | /api/rules/{rule_id}  | Updates an existing rule (including enabling/disabling)    | 4, 5, 6           |
    | DELETE      | /api/rules/{rule_id}  | Deletes an automation rule                                 | 4                 |

- DB STRUCTURE: 

**_rules_** : | **_id_** | name | description | condition_json action_json | is_active | created_at | updated_at |

## API-Gateway

Provides a single entry point for the frontend, exposing REST and WebSocket APIs and proxying requests to internal services and the simulator.

### USER STORIES:

1. As an operator, I want to read sensors data, so that I can monitor the habitat  
3. As an operator, I want to create automation rules, so that I can automate the habitat  
4. As an operator, I want to edit/delete existing automation rules, so that I can modify the behavior of the habitat  
5. As an operator, I want to switch on/off automation rules, so that I can modify the behavior of the habitat  
7. As an operator, I want to interact manually with actuators, so that I can directly control the habitat  
8. As an operator, I want to see the latest sensor readings, so that I can react immediately to critical changes in the habitat  
9. As an operator, I want to check sensors status, so that I can detect malfunctions  
11. As the software, I want to show conflicts between automator rules, so that the operator can solve the issue  

### PORTS:

8003:8000

### DESCRIPTION:

The API-Gateway container acts as the side between the frontend and the internal backend services.  
It exposes a WebSocket endpoint that streams real-time events to the UI, proxies REST calls related to sensor state, rule management, and conflicts to the Processor-Service, and forwards actuator commands to the simulator.

### PERSISTANCE EVALUATION

The API-Gateway container is fully stateless and does not require data persistence.  
All stateful information is managed by the Processor-Service, simulator, and message broker.

### EXTERNAL SERVICES CONNECTIONS

The API-Gateway container connects to:
- The **Processor-Service** via HTTP to proxy state, rules and conflicts endpoints.
- The **Mars IoT Simulator** via HTTP to proxy actuator commands.
- The **RabbitMQ** broker indirectly via a WebSocket manager component that listens to events and broadcasts them to connected WebSocket clients.

### MICROSERVICES:

#### MICROSERVICE: api-gateway

- TYPE: middleware  
- DESCRIPTION: Single entry point for the frontend, exposing WebSocket and REST APIs and proxying calls to the Processor-Service and simulator.  
- PORTS: 8000  
- TECHNOLOGICAL SPECIFICATION:
  - Implemented in Python using FastAPI.
  - Uses `aiohttp` as async HTTP client to proxy requests.
  - Uses a WebSocket manager component to bridge RabbitMQ events to WebSocket clients.
  - CORS enabled for browser access from the frontend.
- SERVICE ARCHITECTURE:
  - A **lifespan** handler initializes an `aiohttp` client session and starts a RabbitMQ-to-WebSocket bridge task.
  - A **WebSocket endpoint** (`/ws`) manages client connections and broadcasts events received from RabbitMQ.
  - A set of **proxy endpoints** under `/api` forward requests to the Processor-Service (state, rules, conflicts) and to the simulator (actuators).

- ENDPOINTS:

    | HTTP METHOD | URL                         | Description                                                  | User Stories          |
    |-------------|-----------------------------|--------------------------------------------------------------|-----------------------|
    | GET         | /health                     | Returns health status of the API-Gateway                     | -                     |
    | WS          | /ws                         | Streams real-time events to the frontend                     | 1, 8, 9, 10, 11       |
    | GET         | /api/state                  | Proxies request for full sensor state to Processor-Service   | 1, 8, 9, 10           |
    | GET         | /api/state/{source}         | Proxies request for a single sensor state                    | 1, 8, 9               |
    | GET         | /api/conflicts              | Proxies request for active rule conflicts                    | 11                    |
    | GET         | /api/rules                  | Proxies list of automation rules                             | 3, 4, 5, 6            |
    | GET         | /api/rules/{rule_id}        | Proxies single rule retrieval                                | 3, 4, 5, 6            |
    | POST        | /api/rules                  | Proxies rule creation                                        | 3, 6                  |
    | PUT         | /api/rules/{rule_id}        | Proxies rule update (including enabling/disabling)           | 4, 5, 6               |
    | DELETE      | /api/rules/{rule_id}        | Proxies rule deletion                                        | 4                     |
    | GET         | /api/actuators              | Proxies list of actuators from the simulator                 | 7                     |
    | POST        | /api/actuators/{actuator}   | Proxies actuator command to the simulator                    | 7                     |

## Frontend

Provides the web dashboard for operators to monitor the habitat, manage automation rules, and interact with actuators.

### USER STORIES:

1. As an operator, I want to read sensors data, so that I can monitor the habitat  
3. As an operator, I want to create automation rules, so that I can automate the habitat  
4. As an operator, I want to edit/delete existing automation rules, so that I can modify the behavior of the habitat  
5. As an operator, I want to switch on/off automation rules, so that I can modify the behavior of the habitat  
7. As an operator, I want to interact manually with actuators, so that I can directly control the habitat  
8. As an operator, I want to see the latest sensor readings, so that I can react immediately to critical changes in the habitat  
9. As an operator, I want to check sensors status, so that I can detect malfunctions  
10. As an operator, I want to see the evolution of sensors data, so that I can understand the behavior of the habitat  
11. As the software, I want to show conflicts between automator rules, so that the operator can solve the issue  

### PORTS:

3000:80

### DESCRIPTION:

The Frontend container serves a single-page React application that connects to the API-Gateway REST and WebSocket endpoints.  
It visualizes live sensor cards grouped by location, shows actuator states and allows manual toggling, and exposes a UI for creating, editing, enabling/disabling, and deleting automation rules.  
Through live charts and conflict indicators, it helps operators quickly understand the current habitat conditions and detect problematic rule interactions.

### PERSISTANCE EVALUATION

The Frontend container does not include a database or persistent application state on the server side.  
All persisted data are stored in backend services; the frontend keeps only in-memory UI state in the browser.

### EXTERNAL SERVICES CONNECTIONS

The Frontend container connects to:
- The **API-Gateway** via HTTP (`/api/...`) to fetch sensor state, rules, conflicts, and actuators, and to send rule/actuator commands.
- The **API-Gateway** via WebSocket (`/ws`) to receive real-time events about sensors, actuators, and rule conflicts.

### MICROSERVICES:

#### MICROSERVICE: frontend

- TYPE: frontend  
- DESCRIPTION: React-based SPA that provides the main operator dashboard for monitoring and controlling the Mars habitat.  
- PORTS: 80  
- TECHNOLOGICAL SPECIFICATION:
  - Implemented in React with Vite as the build tool.
  - Served by nginx, which also proxies `/api` and `/ws` requests to the API-Gateway.
  - Uses the Fetch API for REST calls and the browser WebSocket API for real-time updates.
- SERVICE ARCHITECTURE:
  - A main `App` component that:
    - Manages WebSocket connection status and last received event.
    - Fetches initial state for sensors, rules, actuators, and conflicts via REST.
    - Maintains in-memory histories for sensor values to render mini charts.
  - **Sensors panel**: displays cards/list of sensors with status, last update time, and a mini chart of recent values.
  - **Actuators panel**: shows actuator tiles with ON/OFF state and allows manual toggling.
  - **Rules panel**: lists automation rules, indicates conflicts, and provides create/edit/delete and enable/disable interactions via a modal form.

- ENDPOINTS / PAGES:

    | Name   | Path | Description                                                                 | Related Services | User Stories                        |
    |--------|------|-----------------------------------------------------------------------------|------------------|--------------------------------------|
    | App.jsx| `/`  | Main dashboard with sensors, actuators, and rules management UI            | API-Gateway      | 1, 3, 4, 5, 7, 8, 9, 10, 11          |

## Simulator

Provides the simulated Mars habitat environment that generates sensor data and exposes actuators.

### USER STORIES:

1. As an operator, I want to read sensors data, so that I can monitor the habitat  
7. As an operator, I want to interact manually with actuators, so that I can directly control the habitat  
8. As an operator, I want to see the latest sensor readings, so that I can react immediately to critical changes in the habitat  
9. As an operator, I want to check sensors status, so that I can detect malfunctions  
10. As an operator, I want to see the evolution of sensors data, so that I can understand the behavior of the habitat  

### PORTS:

8080:8080

### DESCRIPTION:

The Simulator container is an external service provided as part of the project template.  
It emulates the Mars habitat by exposing sensor endpoints that the Ingestion-Service polls, and actuator endpoints that receive commands from the Processor-Service or API-Gateway.  
It is the original source of truth for sensor values and the target for actuator commands in the system.

### PERSISTANCE EVALUATION

Persistence details of the Simulator are implementation-specific and outside the scope of this project; for our architecture, the simulator is treated as an external black-box service that can be restarted without impacting our internal persistence guarantees.

### EXTERNAL SERVICES CONNECTIONS

The Simulator container does not connect to other external services inside our stack; instead, other containers (Ingestion-Service, Processor-Service, API-Gateway) connect to it.

### MICROSERVICES:

#### MICROSERVICE: simulator

- TYPE: external / backend  
- DESCRIPTION: Simulates the Mars habitat sensors and actuators exposed over HTTP.  
- PORTS: 8080  
- TECHNOLOGICAL SPECIFICATION:
  - Packaged as a pre-built Docker image (`mars-iot-simulator:multiarch_v1`).
  - Exposes REST endpoints for sensors and actuators.
- SERVICE ARCHITECTURE:
  - Not detailed here, as it is provided and not part of the implemented codebase.

- DB STRUCTURE:

    Not documented, external.

## RabbitMQ

Provides the message broker used to decouple ingestion, processing, and real-time streaming of events.

### USER STORIES:

1. As an operator, I want to read sensors data, so that I can monitor the habitat  
2. As an operator, I want to normalize sensors data, so that I can process them  
3. As an operator, I want to create automation rules, so that I can automate the habitat  
4. As an operator, I want to edit/delete existing automation rules, so that I can modify the behavior of the habitat  
5. As an operator, I want to switch on/off automation rules, so that I can modify the behavior of the habitat  
6. As an operator, I want to save automation rules, so that they persist after a restart  
8. As an operator, I want to see the latest sensor readings, so that I can react immediately to critical changes in the habitat  
9. As an operator, I want to check sensors status, so that I can detect malfunctions  
11. As the software, I want to show conflicts between automator rules, so that the operator can solve the issue  

### PORTS:

5672:5672  
15672:15672

### DESCRIPTION:

The RabbitMQ container hosts the message broker that transports normalized events and derived events between services.  
The Ingestion-Service publishes normalized `UnifiedEvent` messages, the Processor-Service consumes them to update state and evaluate rules, and publishes additional events such as actuator commands, conflicts, and alerts which are then broadcast to the frontend via the API-Gateway.

### PERSISTANCE EVALUATION

For the purposes of this project, RabbitMQ is used as a transient event bus and does not require durable storage beyond the container lifecycle.  
If the broker is restarted, services reconnect and resume streaming current sensor data from the simulator.

### EXTERNAL SERVICES CONNECTIONS

The RabbitMQ container accepts connections from:
- The **Ingestion-Service** as a publisher of normalized events.
- The **Processor-Service** as both consumer and publisher of events.
- The **API-Gateway** (indirectly, via its WebSocket manager) to subscribe to events for the frontend.

### MICROSERVICES:

#### MICROSERVICE: rabbitmq

- TYPE: infrastructure / message broker  
- DESCRIPTION: AMQP message broker that routes events between services.  
- PORTS: 5672, 15672  
- TECHNOLOGICAL SPECIFICATION:
  - Based on the official `rabbitmq:3-management` Docker image.
  - Exposes the AMQP port (`5672`) and management UI (`15672`).
- SERVICE ARCHITECTURE:
  - Standard RabbitMQ broker; internal exchanges/queues (e.g. `mars.events`, `processor.events`) are configured by the services at runtime.

- DB STRUCTURE:

    Uses RabbitMQ’s internal storage mechanisms; no project-specific schema.
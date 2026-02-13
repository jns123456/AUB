# AUB - Gestion de Torneos y Rankings AUB

Aplicación web para la **Asociación Uruguaya de Bridge (AUB)** que permite equilibrar la asignación de direcciones Norte-Sur / Este-Oeste en torneos de bridge, balanceando los handicaps de las parejas.

## El problema

En un torneo de bridge, las parejas juegan en dirección **Norte-Sur (NS)** o **Este-Oeste (EO)**. Si la asignación es aleatoria, puede ocurrir que todos los jugadores fuertes caigan del mismo lado, generando un torneo desbalanceado. Esta aplicación resuelve ese problema asignando direcciones de forma que el **promedio de handicap** sea lo más parejo posible entre ambos sentidos.

## Funcionalidades

### Gestión de jugadores
- Alta, edición y eliminación de jugadores
- Campos: nombre, apellido, handicap, puntos, campeonatos nacionales (CN) y categoría
- Búsqueda y ordenamiento por cualquier columna
- Importación masiva desde **CSV** o **Excel (.xlsx)** con detección automática de columnas

### Importación inteligente de datos
- Detección automática de encabezados (Nombre, Apellido, HCP, Puntos, CN Totales, Categoría)
- Separación automática de columnas combinadas "Apellido Nombre"
- Vista previa antes de confirmar la importación
- Actualización de jugadores existentes si ya están en la base

### Torneos
- Creación de torneos con fecha
- Armado de parejas con **buscador de jugadores** por nombre o apellido
- Cálculo automático del handicap promedio de cada pareja

### Algoritmo de equilibrado
- **Óptimo (fuerza bruta)**: para torneos de hasta 22 parejas, evalúa todas las combinaciones posibles y garantiza el mejor balance
- **Greedy con búsqueda local**: para torneos más grandes, usa una heurística eficiente
- **Re-equilibrado aleatorio**: cada ejecución genera una asignación diferente entre las soluciones igualmente óptimas
- Visualización de promedios NS vs EO y diferencia resultante

### API REST
- Endpoints CRUD para jugadores, torneos, parejas y resultados
- Autenticación JWT + Auth0
- Documentación interactiva vía DRF browsable API
- Filtrado, búsqueda y paginación integrados

## Tecnologías

### Backend

| Componente | Tecnología |
|---|---|
| Framework web | Django 5.x |
| API REST | Django REST Framework |
| Base de datos (producción) | PostgreSQL |
| Base de datos (desarrollo) | SQLite |
| Autenticación | JWT (SimpleJWT) + Auth0 |
| Parsing Excel | openpyxl |

### Frontend

| Componente | Tecnología |
|---|---|
| Interactividad | HTMX |
| Reactividad | Alpine.js |
| Estilos | TailwindCSS |
| Iconos | Bootstrap Icons |

## Instalación

```bash
# Clonar el repositorio
git clone https://github.com/jns123456/AUB.git
cd AUB

# Crear y activar entorno virtual
python -m venv venv
source venv/bin/activate        # macOS / Linux
# venv\Scripts\activate         # Windows

# Instalar dependencias
pip install -r requirements.txt

# Configurar variables de entorno
cp .env.example .env
# Editar .env con tus credenciales

# Aplicar migraciones
python manage.py migrate

# Ejecutar la aplicación
python manage.py runserver
```

La aplicación estará disponible en **http://127.0.0.1:8000**

## Configuración de Base de Datos

### Desarrollo (SQLite - por defecto)
No requiere configuración adicional. SQLite se usa automáticamente si no se define `DATABASE_URL`.

### Producción (PostgreSQL)
Definir la variable de entorno `DATABASE_URL`:
```
DATABASE_URL=postgres://usuario:password@host:5432/nombre_db
```

## Configuración de Auth0

1. Crear una aplicación en [Auth0](https://auth0.com/)
2. Configurar las variables en `.env`:
```
AUTH0_DOMAIN=tu-tenant.auth0.com
AUTH0_CLIENT_ID=tu-client-id
AUTH0_CLIENT_SECRET=tu-client-secret
```
3. En Auth0, configurar las URLs de callback:
   - Allowed Callback URLs: `http://localhost:8000/auth/complete/auth0/`
   - Allowed Logout URLs: `http://localhost:8000/`

## API REST

La API está disponible en `/api/` con los siguientes endpoints:

| Endpoint | Métodos | Descripción |
|---|---|---|
| `/api/jugadores/` | GET, POST | Listar/crear jugadores |
| `/api/jugadores/{id}/` | GET, PUT, DELETE | Detalle de jugador |
| `/api/jugadores/buscar/` | GET | Búsqueda rápida |
| `/api/torneos/` | GET, POST | Listar/crear torneos |
| `/api/torneos/{id}/` | GET, PUT, DELETE | Detalle de torneo |
| `/api/torneos/{id}/equilibrar/` | POST | Equilibrar torneo |
| `/api/torneos/{id}/reset/` | POST | Resetear equilibrado |
| `/api/parejas/` | GET, POST | Parejas de torneo |
| `/api/resultados/` | GET | Resultados importados |
| `/api/manos/` | GET | Manos jugadas |
| `/api/token/` | POST | Obtener JWT |
| `/api/token/refresh/` | POST | Refrescar JWT |

## Estructura del proyecto

```
AUB/
├── aub_project/
│   ├── settings.py         # Configuración Django + DRF + Auth0
│   ├── urls.py             # URLs raíz (admin, API, auth, frontend)
│   ├── wsgi.py             # WSGI config
│   └── asgi.py             # ASGI config
├── bridge/
│   ├── models.py           # Modelos (Jugador, Torneo, ParejaTorneo, etc.)
│   ├── views.py            # Vistas del frontend (FBVs)
│   ├── api_views.py        # ViewSets de la API REST
│   ├── serializers.py      # Serializers DRF
│   ├── urls.py             # URLs del frontend
│   ├── api_urls.py         # URLs de la API REST
│   ├── algorithm.py        # Algoritmo de equilibrado
│   ├── parsers.py          # Parsers de archivos
│   ├── admin.py            # Configuración admin
│   └── templatetags/
│       └── bridge_tags.py  # Template tags personalizados
├── templates/
│   ├── base.html           # Template base (TailwindCSS + HTMX + Alpine.js)
│   ├── index.html          # Página principal
│   ├── jugadores.html      # Gestión de jugadores
│   ├── cargar_base.html    # Importación de base de handicaps
│   ├── torneos.html        # Lista de torneos
│   ├── torneo_nuevo.html   # Crear torneo
│   ├── torneo_detalle.html # Detalle, parejas y equilibrado
│   ├── torneo_acciones.html# Acciones del torneo
│   ├── ranking.html        # Ranking anual
│   └── ...                 # Otros templates
├── static/
│   └── css/
│       └── style.css       # Estilos personalizados
├── requirements.txt        # Dependencias Python
├── .env.example            # Variables de entorno ejemplo
└── manage.py               # Django management
```

## Uso rápido

1. **Cargar base de handicaps**: subir el Excel/CSV con los jugadores y sus handicaps desde la sección "Cargar Base"
2. **Crear torneo**: ir a "Nuevo Torneo" y asignarle nombre y fecha
3. **Armar parejas**: en el detalle del torneo, buscar jugadores por nombre y armar las parejas
4. **Equilibrar**: presionar "Equilibrar Torneo" para asignar direcciones NS/EO balanceadas
5. **Re-equilibrar**: si se desea otra asignación, presionar "Re-Equilibrar" para obtener una nueva distribución diferente

## Handicaps

El sistema de handicaps de la AUB va de **-1** (mejor nivel, categoría Gran Maestro) a valores más altos para jugadores de menor nivel. El handicap de una pareja es el **promedio simple** de los handicaps de sus dos integrantes.

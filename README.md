# AUB - Equilibrador de Torneos de Bridge

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

## Tecnologías

| Componente | Tecnología |
|---|---|
| Backend | Python 3 + Flask |
| Base de datos | SQLite + SQLAlchemy |
| Frontend | Bootstrap 5 + Jinja2 |
| Parsing Excel | openpyxl |

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

# Ejecutar la aplicación
python manage.py runserver
```

La aplicación estará disponible en **http://127.0.0.1:5000**

## Estructura del proyecto

```
AUB/
├── app.py              # Aplicación Flask principal (rutas y lógica)
├── models.py           # Modelos SQLAlchemy (Jugador, Torneo, ParejaTorneo)
├── algorithm.py        # Algoritmo de equilibrado de parejas
├── requirements.txt    # Dependencias Python
├── static/
│   └── css/
│       └── style.css   # Estilos personalizados
└── templates/
    ├── base.html             # Template base con navbar
    ├── index.html            # Página principal
    ├── jugadores.html        # Gestión de jugadores
    ├── cargar_base.html      # Importación de base de handicaps
    ├── torneos.html          # Lista de torneos
    ├── torneo_nuevo.html     # Crear torneo
    └── torneo_detalle.html   # Detalle, parejas y equilibrado
```

## Uso rápido

1. **Cargar base de handicaps**: subir el Excel/CSV con los jugadores y sus handicaps desde la sección "Cargar Base"
2. **Crear torneo**: ir a "Nuevo Torneo" y asignarle nombre y fecha
3. **Armar parejas**: en el detalle del torneo, buscar jugadores por nombre y armar las parejas
4. **Equilibrar**: presionar "Equilibrar Torneo" para asignar direcciones NS/EO balanceadas
5. **Re-equilibrar**: si se desea otra asignación, presionar "Re-Equilibrar" para obtener una nueva distribución diferente

## Handicaps

El sistema de handicaps de la AUB va de **-1** (mejor nivel, categoría Gran Maestro) a valores más altos para jugadores de menor nivel. El handicap de una pareja es el **promedio simple** de los handicaps de sus dos integrantes.

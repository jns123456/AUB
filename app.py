"""
Aplicación Flask para la AUB - Asociación Uruguaya de Bridge.
Equilibrado de torneos de bridge por handicap.
"""

import csv
import io
import json
from datetime import date

from flask import Flask, render_template, request, redirect, url_for, flash

import openpyxl

from models import db, Jugador, Torneo, ParejaTorneo, ResultadoImportado, RankingImportado, ManoJugada
from algorithm import equilibrar_parejas
from parsers import parsear_ranks, parsear_travellers, emparejar_jugadores, calcular_puntos_ranking

app = Flask(__name__)
app.config['SECRET_KEY'] = 'aub-bridge-secret-key-cambiar-en-produccion'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///aub_bridge.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

with app.app_context():
    db.create_all()
    # Migración: agregar columnas nuevas si no existen (SQLite)
    from sqlalchemy import inspect, text
    inspector = inspect(db.engine)

    if 'jugadores' in inspector.get_table_names():
        columnas_existentes = {c['name'] for c in inspector.get_columns('jugadores')}
        with db.engine.connect() as conn:
            if 'puntos' not in columnas_existentes:
                conn.execute(text('ALTER TABLE jugadores ADD COLUMN puntos FLOAT DEFAULT 0'))
            if 'cn_totales' not in columnas_existentes:
                conn.execute(text('ALTER TABLE jugadores ADD COLUMN cn_totales INTEGER DEFAULT 0'))
            if 'categoria' not in columnas_existentes:
                conn.execute(text("ALTER TABLE jugadores ADD COLUMN categoria VARCHAR(50) DEFAULT ''"))
            conn.commit()

    if 'torneos' in inspector.get_table_names():
        cols_torneos = {c['name'] for c in inspector.get_columns('torneos')}
        with db.engine.connect() as conn:
            if 'tipo' not in cols_torneos:
                conn.execute(text("ALTER TABLE torneos ADD COLUMN tipo VARCHAR(50) DEFAULT 'handicap'"))
            conn.commit()

    if 'parejas_torneo' in inspector.get_table_names():
        cols_parejas = {c['name'] for c in inspector.get_columns('parejas_torneo')}
        with db.engine.connect() as conn:
            if 'posicion_final' not in cols_parejas:
                conn.execute(text('ALTER TABLE parejas_torneo ADD COLUMN posicion_final INTEGER'))
            if 'porcentaje' not in cols_parejas:
                conn.execute(text('ALTER TABLE parejas_torneo ADD COLUMN porcentaje FLOAT'))
            if 'puntos_ranking' not in cols_parejas:
                conn.execute(text('ALTER TABLE parejas_torneo ADD COLUMN puntos_ranking FLOAT DEFAULT 0'))
            conn.commit()

    # Crear tablas para resultados importados si no existen
    # (db.create_all() ya las crea, pero esto es para asegurar)


# =============================================================================
# TABLAS DE PUNTOS DE RANKING (Reglamento AUB, Art. 38 y 40)
# =============================================================================

TABLAS_PUNTOS = {
    # Torneos de Parejas con Hándicap (Art. 38) - por viento
    'handicap': [10, 5, 3, 1],
    # Hándicap en Clubes 6+ mesas (Art. 38.B) - por viento
    'handicap_clubes_6': [3, 2, 1],
    # Hándicap en Clubes Howell (Art. 38.B)
    'handicap_clubes_howell': [4, 2, 1],
    # Final Con Hándicap (1 noche)
    'handicap_final': [15, 10, 5, 3],
    # CN Parejas Seleccionadas
    'cn_seleccionadas': [180, 140, 110, 80, 60, 50, 40, 30],
    # CN Parejas Libres
    'cn_libres': [140, 100, 80, 60, 50, 40, 30, 20],
    # CN Parejas Mixtas
    'cn_mixtas': [90, 60, 40, 25, 15, 10, 5],
    # CP Fuerza Limitada
    'cp_fuerza_limitada': [80, 50, 30, 15, 10],
    # Torneo Paralelo PL
    'torneo_paralelo': [20, 15, 10, 5],
    # CN Equipos Libres
    'cn_equipos_libres': [180, 130, 90, 60, 30, 20],
    # CN Equipos Mixtos
    'cn_equipos_mixtos': [90, 60, 40, 20, 10],
    # Equipos Butler
    'equipos_butler': [15, 12, 9, 7, 6],
    # Equipos con Hándicap
    'equipos_handicap': [15, 10, 5, 3],
    # Superior
    'superior': [70, 50, 30, 20, 10, 5],
    # Paralelo
    'paralelo': [20, 15, 10, 5, 3],
}

TIPOS_TORNEO = {
    'handicap': 'Parejas con Hándicap (Art. 38)',
    'handicap_clubes_6': 'Hándicap Clubes 6+ mesas (Art. 38.B)',
    'handicap_clubes_howell': 'Hándicap Clubes Howell (Art. 38.B)',
    'handicap_final': 'Final con Hándicap (1 noche)',
    'cn_seleccionadas': 'CN Parejas Seleccionadas',
    'cn_libres': 'CN Parejas Libres',
    'cn_mixtas': 'CN Parejas Mixtas',
    'cp_fuerza_limitada': 'CP Fuerza Limitada',
    'torneo_paralelo': 'Torneo Paralelo PL',
    'cn_equipos_libres': 'CN Equipos Libres',
    'cn_equipos_mixtos': 'CN Equipos Mixtos',
    'equipos_butler': 'Equipos Butler',
    'equipos_handicap': 'Equipos con Hándicap',
    'superior': 'Superior',
    'paralelo': 'Paralelo',
}


# =============================================================================
# RUTAS PRINCIPALES
# =============================================================================

@app.route('/')
def index():
    """Página principal."""
    total_jugadores = Jugador.query.filter_by(activo=True).count()
    total_torneos = Torneo.query.count()
    torneos_recientes = Torneo.query.order_by(Torneo.fecha.desc()).limit(5).all()
    return render_template('index.html',
                           total_jugadores=total_jugadores,
                           total_torneos=total_torneos,
                           torneos_recientes=torneos_recientes)


# =============================================================================
# RUTAS DE JUGADORES
# =============================================================================

@app.route('/jugadores')
def jugadores():
    """Lista de jugadores."""
    lista = Jugador.query.filter_by(activo=True).order_by(Jugador.apellido, Jugador.nombre).all()
    return render_template('jugadores.html', jugadores=lista)


@app.route('/jugadores/nuevo', methods=['POST'])
def jugador_nuevo():
    """Crear un nuevo jugador."""
    nombre = request.form.get('nombre', '').strip()
    apellido = request.form.get('apellido', '').strip()
    handicap = request.form.get('handicap', '0').strip()

    if not nombre or not apellido:
        flash('Nombre y apellido son obligatorios.', 'danger')
        return redirect(url_for('jugadores'))

    try:
        handicap = float(handicap)
    except ValueError:
        flash('El handicap debe ser un número válido.', 'danger')
        return redirect(url_for('jugadores'))

    try:
        puntos = float(request.form.get('puntos', 0) or 0)
    except (ValueError, TypeError):
        puntos = 0
    try:
        cn_totales = int(float(request.form.get('cn_totales', 0) or 0))
    except (ValueError, TypeError):
        cn_totales = 0
    categoria = request.form.get('categoria', '').strip()

    jugador = Jugador(
        nombre=nombre, apellido=apellido, handicap=handicap,
        puntos=puntos, cn_totales=cn_totales, categoria=categoria,
    )
    db.session.add(jugador)
    db.session.commit()

    flash(f'Jugador {jugador.nombre_completo} agregado exitosamente.', 'success')
    return redirect(url_for('jugadores'))


@app.route('/jugadores/<int:id>/editar', methods=['POST'])
def jugador_editar(id):
    """Editar un jugador existente."""
    jugador = Jugador.query.get_or_404(id)

    nombre = request.form.get('nombre', '').strip()
    apellido = request.form.get('apellido', '').strip()
    handicap = request.form.get('handicap', '0').strip()

    if not nombre or not apellido:
        flash('Nombre y apellido son obligatorios.', 'danger')
        return redirect(url_for('jugadores'))

    try:
        handicap = float(handicap)
    except ValueError:
        flash('El handicap debe ser un número válido.', 'danger')
        return redirect(url_for('jugadores'))

    try:
        puntos = float(request.form.get('puntos', 0) or 0)
    except (ValueError, TypeError):
        puntos = 0
    try:
        cn_totales = int(float(request.form.get('cn_totales', 0) or 0))
    except (ValueError, TypeError):
        cn_totales = 0
    categoria = request.form.get('categoria', '').strip()

    jugador.nombre = nombre
    jugador.apellido = apellido
    jugador.handicap = handicap
    jugador.puntos = puntos
    jugador.cn_totales = cn_totales
    jugador.categoria = categoria
    db.session.commit()

    flash(f'Jugador {jugador.nombre_completo} actualizado.', 'success')
    return redirect(url_for('jugadores'))


@app.route('/jugadores/<int:id>/eliminar', methods=['POST'])
def jugador_eliminar(id):
    """Eliminar (desactivar) un jugador."""
    jugador = Jugador.query.get_or_404(id)
    jugador.activo = False
    db.session.commit()

    flash(f'Jugador {jugador.nombre_completo} eliminado.', 'warning')
    return redirect(url_for('jugadores'))


@app.route('/jugadores/eliminar-todos', methods=['POST'])
def jugadores_eliminar_todos():
    """Eliminar todos los jugadores de la base de datos."""
    # Contar antes de eliminar para el mensaje
    total = Jugador.query.filter_by(activo=True).count()

    if total == 0:
        flash('No hay jugadores para eliminar.', 'info')
        return redirect(url_for('jugadores'))

    # Eliminar todas las parejas de torneo que referencian a jugadores activos
    # (para evitar problemas de integridad referencial)
    ParejaTorneo.query.delete()
    # Resetear estado de todos los torneos
    Torneo.query.update({Torneo.estado: 'configuracion'})
    # Eliminar todos los jugadores (hard delete)
    Jugador.query.delete()
    db.session.commit()

    flash(f'Se eliminaron {total} jugadores de la base de datos.', 'warning')
    return redirect(url_for('jugadores'))


@app.route('/jugadores/importar', methods=['POST'])
def jugadores_importar():
    """Importar jugadores desde un archivo CSV.
    Formato esperado: nombre,apellido,handicap (una fila por jugador).
    """
    archivo = request.files.get('archivo_csv')

    if not archivo or not archivo.filename.endswith('.csv'):
        flash('Por favor, seleccioná un archivo CSV válido.', 'danger')
        return redirect(url_for('jugadores'))

    try:
        contenido = archivo.read().decode('utf-8')
        reader = csv.reader(io.StringIO(contenido))

        count = 0
        for fila in reader:
            if len(fila) < 3:
                continue

            nombre = fila[0].strip()
            apellido = fila[1].strip()

            try:
                handicap = float(fila[2].strip())
            except ValueError:
                continue

            if not nombre or not apellido:
                continue

            # Campos opcionales extra
            puntos = _extraer_campo_float(fila, 3)
            cn_totales = _extraer_campo_int(fila, 4)
            categoria = _extraer_campo_str(fila, 5)

            # Verificar si ya existe
            existente = Jugador.query.filter_by(
                nombre=nombre, apellido=apellido, activo=True
            ).first()

            if existente:
                existente.handicap = handicap
                existente.puntos = puntos
                existente.cn_totales = cn_totales
                existente.categoria = categoria
            else:
                jugador = Jugador(
                    nombre=nombre, apellido=apellido, handicap=handicap,
                    puntos=puntos, cn_totales=cn_totales, categoria=categoria,
                )
                db.session.add(jugador)

            count += 1

        db.session.commit()
        flash(f'Se importaron/actualizaron {count} jugadores exitosamente.', 'success')
    except Exception as e:
        flash(f'Error al importar el archivo: {str(e)}', 'danger')

    return redirect(url_for('jugadores'))


# =============================================================================
# RUTAS DE CARGA DE BASE DE HANDICAPS
# =============================================================================

# Nombres de columnas aceptados para auto-detección
_NOMBRES_NOMBRE = {'nombre', 'name', 'primer nombre', 'first name', 'first_name', 'nombres'}
_NOMBRES_APELLIDO = {'apellido', 'surname', 'last name', 'last_name', 'apellidos'}
_NOMBRES_HANDICAP = {'handicap', 'hcp', 'hc', 'hdcp', 'hándicap'}
_NOMBRES_PUNTOS = {'puntos', 'points', 'pts', 'puntaje', 'score'}
_NOMBRES_CN = {'cn totales', 'cn_totales', 'cn', 'campeonatos', 'campeonatos nacionales',
               'nacionales', 'cn totals'}
_NOMBRES_CATEGORIA = {'categoria', 'categoría', 'category', 'cat', 'nivel', 'level'}
# Columna combinada "Apellido Nombre" en un solo campo
_NOMBRES_COMBINADO = {'nombre', 'name', 'nombres', 'jugador', 'player', 'nombre completo',
                       'nombre y apellido', 'apellido y nombre', 'apellido nombre',
                       'apellido, nombre', 'nombre_completo'}


def _detectar_columnas(headers):
    """Intenta detectar qué columna es cada campo por los nombres de cabecera.

    Usa coincidencia parcial (contains) además de exacta para mayor robustez.

    Returns:
        dict con las claves: col_nombre, col_apellido, col_handicap,
        col_puntos, col_cn, col_categoria, nombre_combinado
    """
    headers_lower = [h.lower().strip() for h in headers]
    cols = {
        'col_nombre': None, 'col_apellido': None, 'col_handicap': None,
        'col_puntos': None, 'col_cn': None, 'col_categoria': None,
    }

    for i, h in enumerate(headers_lower):
        # Limpiar caracteres invisibles / non-breaking spaces
        h = h.replace('\xa0', ' ').replace('\u200b', '').strip()

        if h in _NOMBRES_NOMBRE:
            cols['col_nombre'] = i
        elif h in _NOMBRES_APELLIDO:
            cols['col_apellido'] = i
        elif h in _NOMBRES_HANDICAP:
            cols['col_handicap'] = i
        elif h in _NOMBRES_PUNTOS:
            cols['col_puntos'] = i
        elif h in _NOMBRES_CN:
            cols['col_cn'] = i
        elif h in _NOMBRES_CATEGORIA:
            cols['col_categoria'] = i

    # Segunda pasada: coincidencia parcial para columnas no encontradas
    for i, h in enumerate(headers_lower):
        h = h.replace('\xa0', ' ').replace('\u200b', '').strip()
        if i in (cols['col_nombre'], cols['col_apellido'], cols['col_handicap'],
                 cols['col_puntos'], cols['col_cn'], cols['col_categoria']):
            continue  # Ya asignada
        if cols['col_puntos'] is None and ('punto' in h or 'point' in h):
            cols['col_puntos'] = i
        elif cols['col_cn'] is None and ('cn' in h or 'campeonato' in h or 'nacional' in h):
            cols['col_cn'] = i
        elif cols['col_categoria'] is None and ('categ' in h or 'nivel' in h or 'level' in h):
            cols['col_categoria'] = i
        elif cols['col_handicap'] is None and ('hcp' in h or 'handicap' in h or 'hándicap' in h):
            cols['col_handicap'] = i

    # Si encontramos columna de nombre pero NO de apellido separado,
    # es una columna combinada "Apellido Nombre"
    cols['nombre_combinado'] = cols['col_nombre'] is not None and cols['col_apellido'] is None

    return cols


def _separar_apellido_nombre(valor):
    """Separa un string 'Apellido Nombre' o 'Apellido, Nombre' en (nombre, apellido).

    El formato esperado es Apellido primero, Nombre después.
    Soporta:
        - "Pérez, Juan"       -> nombre=Juan,  apellido=Pérez
        - "Pérez Juan"        -> nombre=Juan,  apellido=Pérez
        - "De Los Santos, Ana"-> nombre=Ana,   apellido=De Los Santos
        - "García López Pedro"-> nombre=Pedro, apellido=García López
    """
    valor = valor.strip()

    if not valor:
        return '', ''

    # Si hay coma, separar por la primera coma: antes = apellido, después = nombre
    if ',' in valor:
        partes = valor.split(',', 1)
        apellido = partes[0].strip()
        nombre = partes[1].strip() if len(partes) > 1 else ''
        return nombre, apellido

    # Sin coma: la última palabra es el nombre, el resto es apellido
    # Esto maneja mejor apellidos compuestos como "De Los Santos Juan"
    partes = valor.split()
    if len(partes) == 1:
        return valor, ''
    elif len(partes) == 2:
        # "Pérez Juan" -> apellido=Pérez, nombre=Juan
        return partes[1], partes[0]
    else:
        # "García López Pedro" -> apellido=García López, nombre=Pedro
        # Última palabra = nombre, resto = apellido
        nombre = partes[-1]
        apellido = ' '.join(partes[:-1])
        return nombre, apellido


def _extraer_campo_float(fila, col_idx):
    """Extrae un valor float de una fila, devuelve 0 si no se puede."""
    if col_idx is None or col_idx >= len(fila):
        return 0
    val = str(fila[col_idx]).strip().replace(',', '.')
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0


def _extraer_campo_int(fila, col_idx):
    """Extrae un valor entero de una fila, devuelve 0 si no se puede."""
    if col_idx is None or col_idx >= len(fila):
        return 0
    val = str(fila[col_idx]).strip().replace(',', '.').replace('.0', '')
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return 0


def _extraer_campo_str(fila, col_idx):
    """Extrae un valor string de una fila, devuelve '' si no se puede."""
    if col_idx is None or col_idx >= len(fila):
        return ''
    val = str(fila[col_idx]).strip()
    return '' if val == 'None' else val


def _encontrar_fila_header(filas, max_buscar=10):
    """Busca la fila que contiene los encabezados en las primeras N filas.

    Returns:
        (indice_header, cols_dict) o (None, None) si no se encuentra.
    """
    for idx in range(min(max_buscar, len(filas))):
        cols = _detectar_columnas(filas[idx])
        # Necesitamos al menos nombre y handicap para considerar que es el header
        if cols['col_nombre'] is not None and cols['col_handicap'] is not None:
            return idx, cols
        # Si encontramos nombre pero no handicap, podría ser la fila correcta
        if cols['col_nombre'] is not None:
            return idx, cols
    return None, None


def _parsear_filas(filas):
    """Parsea filas genéricas (de CSV o Excel) y devuelve lista de dicts con todos los campos."""
    if not filas:
        return []

    # Buscar la fila header en las primeras filas (no asumir que es la primera)
    header_idx, cols = _encontrar_fila_header(filas)

    if header_idx is not None:
        col_nombre = cols['col_nombre']
        col_apellido = cols['col_apellido']
        col_handicap = cols['col_handicap']
        col_puntos = cols['col_puntos']
        col_cn = cols['col_cn']
        col_categoria = cols['col_categoria']
        nombre_combinado = cols['nombre_combinado']
        data_rows = filas[header_idx + 1:]
    else:
        # No se encontró header: asumir orden estándar
        nombre_combinado = False
        col_nombre, col_apellido, col_handicap = 0, 1, 2
        col_puntos = col_cn = col_categoria = None
        if len(filas[0]) >= 3:
            try:
                float(str(filas[0][2]).strip().replace(',', '.'))
                data_rows = filas
            except (ValueError, IndexError):
                data_rows = filas[1:]
        else:
            data_rows = filas

    if col_nombre is None:
        col_nombre = 0
    if not nombre_combinado and col_apellido is None:
        col_apellido = 1
    if col_handicap is None:
        col_handicap = 2 if not nombre_combinado else 1

    resultado = []
    for fila in data_rows:
        cols_necesarias = [col_nombre, col_handicap]
        if not nombre_combinado:
            cols_necesarias.append(col_apellido)
        if len(fila) <= max(c for c in cols_necesarias if c is not None):
            continue

        if nombre_combinado:
            nombre, apellido = _separar_apellido_nombre(str(fila[col_nombre]).strip())
        else:
            nombre = str(fila[col_nombre]).strip()
            apellido = str(fila[col_apellido]).strip()

        if not nombre or not apellido or nombre == 'None' or apellido == 'None':
            continue

        hc_str = str(fila[col_handicap]).strip().replace(',', '.')
        try:
            handicap = float(hc_str)
        except ValueError:
            continue

        puntos_val = _extraer_campo_float(fila, col_puntos)
        cn_val = _extraer_campo_int(fila, col_cn)
        cat_val = _extraer_campo_str(fila, col_categoria)

        resultado.append({
            'nombre': nombre,
            'apellido': apellido,
            'handicap': handicap,
            'puntos': puntos_val,
            'cn_totales': cn_val,
            'categoria': cat_val,
        })

    return resultado


def _parsear_csv(contenido_bytes):
    """Parsea un archivo CSV y devuelve lista de dicts."""
    for encoding in ('utf-8-sig', 'utf-8', 'latin-1', 'cp1252'):
        try:
            contenido = contenido_bytes.decode(encoding)
            break
        except (UnicodeDecodeError, ValueError):
            continue
    else:
        raise ValueError('No se pudo decodificar el archivo. Probá guardándolo como UTF-8.')

    sniffer = csv.Sniffer()
    try:
        dialect = sniffer.sniff(contenido[:2048], delimiters=',;\t|')
    except csv.Error:
        dialect = None

    reader = csv.reader(io.StringIO(contenido), dialect) if dialect else csv.reader(io.StringIO(contenido))
    filas = list(reader)

    return _parsear_filas(filas)


def _parsear_excel(archivo_bytes):
    """Parsea un archivo Excel (.xlsx) y devuelve lista de dicts."""
    wb = openpyxl.load_workbook(io.BytesIO(archivo_bytes), read_only=True, data_only=True)
    ws = wb.active

    filas = []
    for row in ws.iter_rows(values_only=True):
        filas.append([str(cell) if cell is not None else '' for cell in row])

    wb.close()

    return _parsear_filas(filas)


def _generar_preview(datos_parseados):
    """Compara los datos parseados con la base existente y genera un preview."""
    preview = []
    nuevos = 0
    actualizados = 0
    sin_cambios = 0

    for d in datos_parseados:
        nombre = d['nombre']
        apellido = d['apellido']
        existente = Jugador.query.filter_by(
            nombre=nombre, apellido=apellido, activo=True
        ).first()

        item = {
            'nombre': nombre,
            'apellido': apellido,
            'handicap': d['handicap'],
            'puntos': d.get('puntos', 0),
            'cn_totales': d.get('cn_totales', 0),
            'categoria': d.get('categoria', ''),
            'handicap_anterior': None,
        }

        if existente:
            cambio = (existente.handicap != d['handicap'] or
                      existente.puntos != d.get('puntos', 0) or
                      existente.cn_totales != d.get('cn_totales', 0) or
                      (existente.categoria or '') != d.get('categoria', ''))
            if cambio:
                item['estado'] = 'actualizar'
                item['handicap_anterior'] = existente.handicap
                actualizados += 1
            else:
                item['estado'] = 'sin_cambios'
                item['handicap_anterior'] = existente.handicap
                sin_cambios += 1
        else:
            item['estado'] = 'nuevo'
            nuevos += 1

        preview.append(item)

    return preview, nuevos, actualizados, sin_cambios


@app.route('/cargar-base', methods=['GET', 'POST'])
def cargar_base():
    """Página para cargar la base de datos histórica de handicaps."""
    if request.method == 'GET':
        return render_template('cargar_base.html')

    # POST: procesar archivo subido
    archivo = request.files.get('archivo')

    if not archivo or not archivo.filename:
        flash('Por favor, seleccioná un archivo.', 'danger')
        return redirect(url_for('cargar_base'))

    filename = archivo.filename.lower()
    archivo_bytes = archivo.read()

    try:
        if filename.endswith('.csv') or filename.endswith('.txt'):
            datos = _parsear_csv(archivo_bytes)
        elif filename.endswith('.xlsx'):
            datos = _parsear_excel(archivo_bytes)
        else:
            flash('Formato no soportado. Usá archivos .csv o .xlsx', 'danger')
            return redirect(url_for('cargar_base'))
    except Exception as e:
        flash(f'Error al leer el archivo: {str(e)}', 'danger')
        return redirect(url_for('cargar_base'))

    if not datos:
        flash('No se encontraron datos válidos en el archivo. '
              'Verificá que tenga columnas: Nombre, Apellido, Handicap.', 'warning')
        return redirect(url_for('cargar_base'))

    # Generar preview
    preview, nuevos, actualizados, sin_cambios = _generar_preview(datos)

    # Codificar datos para el form de confirmación
    datos_json = json.dumps(datos)

    return render_template('cargar_base.html',
                           preview=preview,
                           datos_json=datos_json,
                           nuevos=nuevos,
                           actualizados=actualizados,
                           sin_cambios=sin_cambios,
                           total=len(preview))


@app.route('/cargar-base/confirmar', methods=['POST'])
def cargar_base_confirmar():
    """Confirma e importa los datos de la vista previa."""
    datos_json = request.form.get('datos_json', '[]')

    try:
        datos = json.loads(datos_json)
    except (json.JSONDecodeError, ValueError):
        flash('Error al procesar los datos. Intentá subir el archivo de nuevo.', 'danger')
        return redirect(url_for('cargar_base'))

    nuevos = 0
    actualizados = 0

    for item in datos:
        nombre = item.get('nombre', '').strip()
        apellido = item.get('apellido', '').strip()
        try:
            handicap = float(item.get('handicap', 0))
        except (ValueError, TypeError):
            continue

        if not nombre or not apellido:
            continue

        try:
            puntos = float(item.get('puntos', 0) or 0)
        except (ValueError, TypeError):
            puntos = 0
        try:
            cn_totales = int(float(item.get('cn_totales', 0) or 0))
        except (ValueError, TypeError):
            cn_totales = 0
        categoria = str(item.get('categoria', '') or '').strip()

        existente = Jugador.query.filter_by(
            nombre=nombre, apellido=apellido, activo=True
        ).first()

        if existente:
            cambio = (existente.handicap != handicap or
                      existente.puntos != puntos or
                      existente.cn_totales != cn_totales or
                      (existente.categoria or '') != categoria)
            if cambio:
                existente.handicap = handicap
                existente.puntos = puntos
                existente.cn_totales = cn_totales
                existente.categoria = categoria
                actualizados += 1
        else:
            jugador = Jugador(
                nombre=nombre, apellido=apellido, handicap=handicap,
                puntos=puntos, cn_totales=cn_totales, categoria=categoria,
            )
            db.session.add(jugador)
            nuevos += 1

    db.session.commit()

    flash(
        f'Base de handicaps importada exitosamente: '
        f'{nuevos} jugadores nuevos, {actualizados} handicaps actualizados.',
        'success'
    )
    return redirect(url_for('jugadores'))


# =============================================================================
# RUTAS DE TORNEOS
# =============================================================================

@app.route('/torneos')
def torneos():
    """Lista de torneos."""
    lista = Torneo.query.order_by(Torneo.fecha.desc()).all()
    return render_template('torneos.html', torneos=lista)


@app.route('/torneo/nuevo', methods=['GET', 'POST'])
def torneo_nuevo():
    """Crear un nuevo torneo."""
    if request.method == 'POST':
        nombre = request.form.get('nombre', '').strip()
        fecha_str = request.form.get('fecha', '')

        if not nombre:
            flash('El nombre del torneo es obligatorio.', 'danger')
            return redirect(url_for('torneo_nuevo'))

        try:
            fecha = date.fromisoformat(fecha_str) if fecha_str else date.today()
        except ValueError:
            fecha = date.today()

        torneo = Torneo(nombre=nombre, fecha=fecha)
        db.session.add(torneo)
        db.session.commit()

        flash(f'Torneo "{torneo.nombre}" creado exitosamente.', 'success')
        return redirect(url_for('torneo_detalle', id=torneo.id))

    return render_template('torneo_nuevo.html', hoy=date.today().isoformat())


@app.route('/torneo/<int:id>')
def torneo_detalle(id):
    """Detalle del torneo: configuración de parejas y resultados."""
    torneo = Torneo.query.get_or_404(id)

    # Obtener jugadores ya asignados a alguna pareja en este torneo
    jugadores_en_parejas = set()
    for pareja in torneo.parejas:
        jugadores_en_parejas.add(pareja.jugador1_id)
        jugadores_en_parejas.add(pareja.jugador2_id)

    # Jugadores disponibles (activos y no asignados)
    jugadores_disponibles = Jugador.query.filter_by(activo=True).order_by(
        Jugador.apellido, Jugador.nombre
    ).all()

    return render_template('torneo_detalle.html',
                           torneo=torneo,
                           jugadores_disponibles=jugadores_disponibles,
                           jugadores_en_parejas=jugadores_en_parejas,
                           tipos_torneo=TIPOS_TORNEO,
                           tablas_puntos=TABLAS_PUNTOS)


@app.route('/torneo/<int:id>/pareja', methods=['POST'])
def torneo_agregar_pareja(id):
    """Agregar una pareja al torneo."""
    torneo = Torneo.query.get_or_404(id)

    jugador1_id = request.form.get('jugador1_id', type=int)
    jugador2_id = request.form.get('jugador2_id', type=int)

    if not jugador1_id or not jugador2_id:
        flash('Debés seleccionar dos jugadores para la pareja.', 'danger')
        return redirect(url_for('torneo_detalle', id=id))

    if jugador1_id == jugador2_id:
        flash('Los dos jugadores de la pareja deben ser diferentes.', 'danger')
        return redirect(url_for('torneo_detalle', id=id))

    # Verificar que los jugadores no estén ya en otra pareja del torneo
    existente = ParejaTorneo.query.filter_by(torneo_id=id).filter(
        db.or_(
            ParejaTorneo.jugador1_id.in_([jugador1_id, jugador2_id]),
            ParejaTorneo.jugador2_id.in_([jugador1_id, jugador2_id]),
        )
    ).first()

    if existente:
        flash('Uno o ambos jugadores ya están asignados a otra pareja en este torneo.', 'danger')
        return redirect(url_for('torneo_detalle', id=id))

    jugador1 = Jugador.query.get_or_404(jugador1_id)
    jugador2 = Jugador.query.get_or_404(jugador2_id)

    pareja = ParejaTorneo(
        torneo_id=id,
        jugador1_id=jugador1_id,
        jugador2_id=jugador2_id,
        handicap_pareja=round((jugador1.handicap + jugador2.handicap) / 2, 2)
    )
    db.session.add(pareja)

    # Si el torneo estaba equilibrado, resetear
    if torneo.estado == 'equilibrado':
        torneo.estado = 'configuracion'
        for p in torneo.parejas:
            p.direccion = None

    db.session.commit()

    flash(f'Pareja {jugador1.nombre_completo} & {jugador2.nombre_completo} agregada.', 'success')
    return redirect(url_for('torneo_detalle', id=id))


@app.route('/torneo/<int:id>/pareja/<int:pareja_id>/eliminar', methods=['POST'])
def torneo_eliminar_pareja(id, pareja_id):
    """Eliminar una pareja del torneo."""
    pareja = ParejaTorneo.query.get_or_404(pareja_id)

    if pareja.torneo_id != id:
        flash('La pareja no pertenece a este torneo.', 'danger')
        return redirect(url_for('torneo_detalle', id=id))

    torneo = Torneo.query.get_or_404(id)

    # Si el torneo estaba equilibrado, resetear
    if torneo.estado == 'equilibrado':
        torneo.estado = 'configuracion'
        for p in torneo.parejas:
            p.direccion = None

    db.session.delete(pareja)
    db.session.commit()

    flash('Pareja eliminada del torneo.', 'warning')
    return redirect(url_for('torneo_detalle', id=id))


@app.route('/torneo/<int:id>/equilibrar', methods=['POST'])
def torneo_equilibrar(id):
    """Ejecutar el algoritmo de equilibrado."""
    torneo = Torneo.query.get_or_404(id)

    if len(torneo.parejas) < 2:
        flash('Se necesitan al menos 2 parejas para equilibrar el torneo.', 'danger')
        return redirect(url_for('torneo_detalle', id=id))

    # Preparar datos para el algoritmo
    datos_parejas = [
        {'id': p.id, 'handicap_pareja': p.handicap_pareja}
        for p in torneo.parejas
    ]

    # Ejecutar el equilibrado
    resultado = equilibrar_parejas(datos_parejas)

    # Asignar direcciones
    ns_ids = {p['id'] for p in resultado['ns']}
    eo_ids = {p['id'] for p in resultado['eo']}

    for pareja in torneo.parejas:
        if pareja.id in ns_ids:
            pareja.direccion = 'NS'
        elif pareja.id in eo_ids:
            pareja.direccion = 'EO'

    torneo.estado = 'equilibrado'
    db.session.commit()

    diferencia = resultado['diferencia']
    flash(
        f'Torneo equilibrado exitosamente. '
        f'Promedio NS: {resultado["ns_promedio"]} | '
        f'Promedio EO: {resultado["eo_promedio"]} | '
        f'Diferencia: {diferencia}',
        'success'
    )
    return redirect(url_for('torneo_detalle', id=id))


@app.route('/torneo/<int:id>/reset', methods=['POST'])
def torneo_reset(id):
    """Resetear el equilibrado del torneo."""
    torneo = Torneo.query.get_or_404(id)
    torneo.estado = 'configuracion'

    for pareja in torneo.parejas:
        pareja.direccion = None

    db.session.commit()

    flash('Equilibrado reseteado. Podés volver a equilibrar.', 'info')
    return redirect(url_for('torneo_detalle', id=id))


@app.route('/torneo/<int:id>/resultados', methods=['POST'])
def torneo_resultados(id):
    """Guardar posiciones finales, porcentajes y calcular puntos de ranking según Art. 38."""
    import math
    torneo = Torneo.query.get_or_404(id)

    if torneo.estado != 'equilibrado':
        flash('El torneo debe estar equilibrado para asignar resultados.', 'danger')
        return redirect(url_for('torneo_detalle', id=id))

    # Guardar tipo de torneo
    tipo = request.form.get('tipo_torneo', 'handicap')
    torneo.tipo = tipo

    tabla = TABLAS_PUNTOS.get(tipo, [])

    # Guardar posiciones, porcentajes y calcular puntos para cada pareja
    for pareja in torneo.parejas:
        pos_str = request.form.get(f'pos_{pareja.id}', '').strip()
        pct_str = request.form.get(f'pct_{pareja.id}', '').strip()

        # Guardar porcentaje
        pareja.porcentaje = None
        if pct_str:
            try:
                pareja.porcentaje = float(pct_str)
            except (ValueError, TypeError):
                pass

        # Guardar posición y calcular puntos
        if pos_str:
            try:
                pos = int(pos_str)
                pareja.posicion_final = pos

                # Cálculo según Art. 38 para torneos de hándicap
                if tipo == 'handicap' and pareja.porcentaje is not None:
                    pct = pareja.porcentaje
                    if pos <= 4:  # Solo top 4 por viento reciben puntos
                        if pct >= 58:
                            # >= 58%: puntos = % - 50, redondeado hacia arriba
                            pareja.puntos_ranking = math.ceil(pct - 50)
                        elif pct >= 50:
                            # 50% - 57.99%: puntos fijos según posición
                            if pos <= len(tabla):
                                pareja.puntos_ranking = tabla[pos - 1]
                            else:
                                pareja.puntos_ranking = 0
                        else:
                            # < 50%: sin puntos
                            pareja.puntos_ranking = 0
                    else:
                        pareja.puntos_ranking = 0
                else:
                    # Otros tipos de torneo: usar tabla directa
                    if 1 <= pos <= len(tabla):
                        pareja.puntos_ranking = tabla[pos - 1]
                    else:
                        pareja.puntos_ranking = 0
            except (ValueError, TypeError):
                pareja.posicion_final = None
                pareja.puntos_ranking = 0
        else:
            pareja.posicion_final = None
            pareja.puntos_ranking = 0

    db.session.commit()

    flash('Resultados guardados exitosamente.', 'success')
    return redirect(url_for('torneo_detalle', id=id))


@app.route('/torneo/<int:id>/eliminar', methods=['POST'])
def torneo_eliminar(id):
    """Eliminar un torneo."""
    torneo = Torneo.query.get_or_404(id)
    db.session.delete(torneo)
    db.session.commit()

    flash(f'Torneo "{torneo.nombre}" eliminado.', 'warning')
    return redirect(url_for('torneos'))


# =============================================================================
# RANKING ANUAL
# =============================================================================

@app.route('/ranking')
@app.route('/ranking/<int:anio>')
def ranking(anio=None):
    """Ranking anual de jugadores basado en puntos acumulados en torneos."""
    from sqlalchemy import func, extract

    if anio is None:
        anio = date.today().year

    # Años disponibles (para el selector)
    anios_disponibles = db.session.query(
        extract('year', Torneo.fecha).label('anio')
    ).distinct().order_by(extract('year', Torneo.fecha).desc()).all()
    anios_disponibles = [int(a.anio) for a in anios_disponibles]

    if anio not in anios_disponibles and anios_disponibles:
        anio = anios_disponibles[0]

    # Obtener todos los torneos del año seleccionado que tienen resultados
    torneos_anio = Torneo.query.filter(
        extract('year', Torneo.fecha) == anio,
        Torneo.estado == 'equilibrado',
    ).order_by(Torneo.fecha.desc()).all()

    # Acumular puntos por jugador
    puntos_jugador = {}  # jugador_id -> { jugador, puntos_total, torneos_jugados, detalle }

    for torneo in torneos_anio:
        for pareja in torneo.parejas:
            if not pareja.puntos_ranking or pareja.puntos_ranking <= 0:
                continue

            pts = pareja.puntos_ranking
            tipo_label = TIPOS_TORNEO.get(torneo.tipo, torneo.tipo or '')

            for jugador in [pareja.jugador1, pareja.jugador2]:
                if jugador.id not in puntos_jugador:
                    puntos_jugador[jugador.id] = {
                        'jugador': jugador,
                        'puntos_total': 0,
                        'torneos_jugados': 0,
                        'detalle': [],
                    }

                puntos_jugador[jugador.id]['puntos_total'] += pts
                puntos_jugador[jugador.id]['torneos_jugados'] += 1
                puntos_jugador[jugador.id]['detalle'].append({
                    'torneo': torneo.nombre,
                    'fecha': torneo.fecha,
                    'tipo': tipo_label,
                    'posicion': pareja.posicion_final,
                    'direccion': pareja.direccion,
                    'puntos': pts,
                })

    # Ordenar por puntos descendente
    ranking_list = sorted(
        puntos_jugador.values(),
        key=lambda x: x['puntos_total'],
        reverse=True,
    )

    return render_template('ranking.html',
                           ranking=ranking_list,
                           anio=anio,
                           anios_disponibles=anios_disponibles,
                           total_torneos=len(torneos_anio))


# =============================================================================
# IMPORTACIÓN DE RESULTADOS DE TORNEO
# =============================================================================

@app.route('/torneo/<int:id>/importar-resultados', methods=['GET', 'POST'])
def torneo_importar_resultados(id):
    """Importar resultados de torneo desde archivos Ranks.txt y Travellers.txt."""
    torneo = Torneo.query.get_or_404(id)
    
    if request.method == 'GET':
        return render_template('importar_resultados.html', 
                               torneo=torneo,
                               tipos_torneo=TIPOS_TORNEO)
    
    # POST: procesar archivos subidos
    archivo_ranks = request.files.get('archivo_ranks')
    archivo_travellers = request.files.get('archivo_travellers')
    tipo_torneo = request.form.get('tipo_torneo', 'handicap')
    
    if not archivo_ranks or not archivo_ranks.filename:
        flash('El archivo de Rankings es obligatorio.', 'danger')
        return redirect(url_for('torneo_importar_resultados', id=id))
    
    try:
        # Leer archivos
        contenido_ranks = archivo_ranks.read().decode('utf-8', errors='replace')
        
        contenido_travellers = None
        if archivo_travellers and archivo_travellers.filename:
            contenido_travellers = archivo_travellers.read().decode('utf-8', errors='replace')
        
        # Parsear archivos
        datos_ranks = parsear_ranks(contenido_ranks)
        datos_travellers = parsear_travellers(contenido_travellers) if contenido_travellers else None
        
        if not datos_ranks['rankings']:
            flash('No se encontraron rankings en el archivo.', 'danger')
            return redirect(url_for('torneo_importar_resultados', id=id))
        
        # Eliminar resultado importado anterior si existe
        resultado_anterior = ResultadoImportado.query.filter_by(torneo_id=id).first()
        if resultado_anterior:
            db.session.delete(resultado_anterior)
            db.session.commit()
        
        # Crear nuevo resultado importado
        resultado = ResultadoImportado(
            torneo_id=id,
            nombre_archivo_ranks=archivo_ranks.filename,
            nombre_archivo_travellers=archivo_travellers.filename if archivo_travellers else None,
            session_info=datos_ranks.get('session', ''),
            mesas=datos_ranks.get('mesas'),
            boards_totales=datos_ranks.get('boards'),
            movimiento=datos_ranks.get('movimiento', '')
        )
        db.session.add(resultado)
        db.session.flush()  # Para obtener el ID
        
        # Obtener todos los jugadores para emparejar
        jugadores_db = Jugador.query.filter_by(activo=True).all()
        
        # Guardar rankings
        for r in datos_ranks['rankings']:
            puntos = calcular_puntos_ranking(
                r['posicion'], 
                r['porcentaje_con_handicap'], 
                tipo_torneo
            )
            
            ranking = RankingImportado(
                resultado_id=resultado.id,
                posicion=r['posicion'],
                numero_pareja=r['numero_pareja'],
                nombre_jugador1=r['nombre_jugador1'],
                nombre_jugador2=r['nombre_jugador2'],
                boards_jugados=r['boards_jugados'],
                total_puntos=r['total_puntos'],
                maximo_puntos=r['maximo_puntos'],
                porcentaje=r['porcentaje'],
                handicap=r['handicap'],
                porcentaje_con_handicap=r['porcentaje_con_handicap'],
                puntos_asignados=puntos,
                jugador1_id=emparejar_jugadores(r['nombre_jugador1'], jugadores_db),
                jugador2_id=emparejar_jugadores(r['nombre_jugador2'], jugadores_db)
            )
            db.session.add(ranking)
        
        # Guardar manos jugadas si hay archivo de travellers
        if datos_travellers and datos_travellers['manos']:
            for m in datos_travellers['manos']:
                mano = ManoJugada(
                    resultado_id=resultado.id,
                    board_numero=m['board_numero'],
                    pareja_ns=m['pareja_ns'],
                    pareja_ew=m['pareja_ew'],
                    contrato=m['contrato'],
                    declarante=m['declarante'],
                    salida=m['salida'],
                    puntos_ns_positivo=m['puntos_ns_positivo'],
                    puntos_ns_negativo=m['puntos_ns_negativo'],
                    mp_ns=m['mp_ns'],
                    mp_ew=m['mp_ew'],
                    nombre_pareja_ns=m['nombre_pareja_ns'],
                    nombre_pareja_ew=m['nombre_pareja_ew']
                )
                db.session.add(mano)
        
        # Actualizar tipo de torneo
        torneo.tipo = tipo_torneo
        torneo.estado = 'equilibrado'  # Marcarlo como terminado
        
        db.session.commit()
        
        total_rankings = len(datos_ranks['rankings'])
        total_manos = len(datos_travellers['manos']) if datos_travellers else 0
        
        flash(
            f'Resultados importados exitosamente: {total_rankings} parejas, {total_manos} manos.',
            'success'
        )
        return redirect(url_for('torneo_ver_resultados', id=id))
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error al importar los archivos: {str(e)}', 'danger')
        return redirect(url_for('torneo_importar_resultados', id=id))


@app.route('/torneo/<int:id>/resultados-importados')
def torneo_ver_resultados(id):
    """Ver los resultados importados de un torneo."""
    torneo = Torneo.query.get_or_404(id)
    resultado = ResultadoImportado.query.filter_by(torneo_id=id).first()
    
    if not resultado:
        flash('No hay resultados importados para este torneo.', 'warning')
        return redirect(url_for('torneo_detalle', id=id))
    
    # Obtener rankings ordenados por posición
    rankings = RankingImportado.query.filter_by(resultado_id=resultado.id)\
        .order_by(RankingImportado.posicion).all()
    
    # Obtener estadísticas de manos
    total_boards = db.session.query(db.func.count(db.func.distinct(ManoJugada.board_numero)))\
        .filter(ManoJugada.resultado_id == resultado.id).scalar()
    
    return render_template('ver_resultados.html',
                           torneo=torneo,
                           resultado=resultado,
                           rankings=rankings,
                           total_boards=total_boards,
                           tipos_torneo=TIPOS_TORNEO)


@app.route('/torneo/<int:id>/manos')
@app.route('/torneo/<int:id>/manos/<int:board>')
def torneo_ver_manos(id, board=None):
    """Ver las manos jugadas en un torneo."""
    torneo = Torneo.query.get_or_404(id)
    resultado = ResultadoImportado.query.filter_by(torneo_id=id).first()
    
    if not resultado:
        flash('No hay resultados importados para este torneo.', 'warning')
        return redirect(url_for('torneo_detalle', id=id))
    
    # Obtener lista de boards disponibles
    boards_disponibles = db.session.query(db.func.distinct(ManoJugada.board_numero))\
        .filter(ManoJugada.resultado_id == resultado.id)\
        .order_by(ManoJugada.board_numero).all()
    boards_disponibles = [b[0] for b in boards_disponibles]
    
    if not boards_disponibles:
        flash('No hay manos registradas para este torneo.', 'warning')
        return redirect(url_for('torneo_ver_resultados', id=id))
    
    # Si no se especifica board, mostrar el primero
    if board is None:
        board = boards_disponibles[0]
    
    # Obtener manos del board seleccionado
    manos = ManoJugada.query.filter_by(resultado_id=resultado.id, board_numero=board)\
        .order_by(ManoJugada.mp_ns.desc()).all()
    
    return render_template('ver_manos.html',
                           torneo=torneo,
                           resultado=resultado,
                           board_actual=board,
                           boards_disponibles=boards_disponibles,
                           manos=manos)


@app.route('/torneo/<int:id>/actualizar-puntos', methods=['POST'])
def torneo_actualizar_puntos(id):
    """Actualiza los puntos de ranking de los jugadores basándose en los resultados importados."""
    torneo = Torneo.query.get_or_404(id)
    resultado = ResultadoImportado.query.filter_by(torneo_id=id).first()
    
    if not resultado:
        flash('No hay resultados importados para este torneo.', 'danger')
        return redirect(url_for('torneo_detalle', id=id))
    
    rankings = RankingImportado.query.filter_by(resultado_id=resultado.id).all()
    
    jugadores_actualizados = 0
    
    for ranking in rankings:
        puntos = ranking.puntos_asignados or 0
        
        if puntos > 0:
            # Actualizar jugador 1 si está vinculado
            if ranking.jugador1_id:
                jugador1 = Jugador.query.get(ranking.jugador1_id)
                if jugador1:
                    jugador1.puntos = (jugador1.puntos or 0) + puntos
                    jugadores_actualizados += 1
            
            # Actualizar jugador 2 si está vinculado
            if ranking.jugador2_id:
                jugador2 = Jugador.query.get(ranking.jugador2_id)
                if jugador2:
                    jugador2.puntos = (jugador2.puntos or 0) + puntos
                    jugadores_actualizados += 1
    
    db.session.commit()
    
    flash(f'Se actualizaron los puntos de {jugadores_actualizados} jugadores.', 'success')
    return redirect(url_for('torneo_ver_resultados', id=id))


# =============================================================================
# MAIN
# =============================================================================

if __name__ == '__main__':
    app.run(debug=True, port=5000)

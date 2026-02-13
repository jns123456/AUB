"""
Vistas de la aplicación AUB Bridge.
Migrado de Flask a Django.
"""

import csv
import io
import json
import math
from datetime import date

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db.models import Q, Case, When, Value, IntegerField
from django.db.models.functions import ExtractYear, Coalesce
from django.http import HttpResponse, JsonResponse

import openpyxl

from .models import Jugador, Torneo, ParejaTorneo, ResultadoImportado, RankingImportado, ManoJugada, Lugar
from .algorithm import equilibrar_parejas
from .parsers import parsear_ranks, parsear_travellers, emparejar_jugadores, calcular_puntos_ranking


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

def index(request):
    """Página principal - Dashboard integral de gestión AUB."""
    from django.db.models import Avg, Count, Sum
    from datetime import date

    hoy = date.today()
    anio_actual = hoy.year

    total_jugadores = Jugador.objects.filter(activo=True).count()
    total_torneos = Torneo.objects.count()
    torneos_este_anio = Torneo.objects.filter(fecha__year=anio_actual).count()
    torneos_recientes = Torneo.objects.order_by('-fecha')[:5]

    # Categorías de jugadores para el resumen
    categorias_count = (
        Jugador.objects.filter(activo=True)
        .exclude(categoria__isnull=True)
        .exclude(categoria='')
        .values('categoria')
        .annotate(total=Count('id'))
        .order_by('-total')
    )

    # Último torneo
    ultimo_torneo = Torneo.objects.order_by('-fecha').first()

    # Top jugadores por puntos
    top_jugadores = Jugador.objects.filter(
        activo=True, puntos__gt=0
    ).order_by('-puntos')[:5]

    # Promedio de handicap general
    promedio_handicap = Jugador.objects.filter(activo=True).aggregate(
        promedio=Avg('handicap')
    )['promedio'] or 0

    return render(request, 'index.html', {
        'total_jugadores': total_jugadores,
        'total_torneos': total_torneos,
        'torneos_este_anio': torneos_este_anio,
        'torneos_recientes': torneos_recientes,
        'categorias_count': categorias_count,
        'ultimo_torneo': ultimo_torneo,
        'top_jugadores': top_jugadores,
        'promedio_handicap': round(promedio_handicap, 1),
        'anio_actual': anio_actual,
    })


# =============================================================================
# VISTAS DE JUGADORES
# =============================================================================

def jugadores(request):
    """Lista de jugadores ordenados por Ranking AUB (categoría + puntos)."""
    # Orden de categorías según reglamento AUB
    categoria_orden = Case(
        When(categoria__iexact='GRAN MAESTRO', then=Value(0)),
        When(categoria__iexact='GM', then=Value(0)),
        When(categoria__iexact='MAESTRO', then=Value(1)),
        When(categoria__iexact='SUPERIOR', then=Value(2)),
        When(categoria__iexact='PRIMERA', then=Value(3)),
        When(categoria__iexact='SEGUNDA', then=Value(4)),
        When(categoria__iexact='TERCERA', then=Value(5)),
        When(categoria__iexact='CUARTA', then=Value(6)),
        When(categoria__iexact='QUINTA', then=Value(7)),
        When(categoria__iexact='PRINCIPIANTES', then=Value(8)),
        When(categoria__iexact='PRINCIPIANTE', then=Value(8)),
        default=Value(99),
        output_field=IntegerField(),
    )
    
    # Ordenar por categoría (ascendente) y luego por puntos (descendente)
    lista = Jugador.objects.filter(activo=True).annotate(
        categoria_orden=categoria_orden
    ).order_by('categoria_orden', '-puntos', 'apellido', 'nombre')
    
    return render(request, 'jugadores.html', {'jugadores': lista})


def jugador_nuevo(request):
    """Crear un nuevo jugador."""
    if request.method != 'POST':
        return redirect('jugadores')
    
    nombre = request.POST.get('nombre', '').strip()
    apellido = request.POST.get('apellido', '').strip()
    handicap = request.POST.get('handicap', '0').strip()

    if not nombre or not apellido:
        messages.error(request, 'Nombre y apellido son obligatorios.')
        return redirect('jugadores')

    try:
        handicap = float(handicap)
    except ValueError:
        messages.error(request, 'El handicap debe ser un número válido.')
        return redirect('jugadores')

    try:
        puntos = float(request.POST.get('puntos', 0) or 0)
    except (ValueError, TypeError):
        puntos = 0
    try:
        cn_totales = int(float(request.POST.get('cn_totales', 0) or 0))
    except (ValueError, TypeError):
        cn_totales = 0
    categoria = request.POST.get('categoria', '').strip()
    es_director = request.POST.get('es_director') == '1'

    jugador = Jugador(
        nombre=nombre, apellido=apellido, handicap=handicap,
        puntos=puntos, cn_totales=cn_totales, categoria=categoria,
        es_director=es_director,
    )
    jugador.save()

    messages.success(request, f'Jugador {jugador.nombre_completo} agregado exitosamente.')
    return redirect('jugadores')


def jugador_editar(request, id):
    """Editar un jugador existente."""
    if request.method != 'POST':
        return redirect('jugadores')
    
    jugador = get_object_or_404(Jugador, id=id)

    nombre = request.POST.get('nombre', '').strip()
    apellido = request.POST.get('apellido', '').strip()
    handicap = request.POST.get('handicap', '0').strip()

    if not nombre or not apellido:
        messages.error(request, 'Nombre y apellido son obligatorios.')
        return redirect('jugadores')

    try:
        handicap = float(handicap)
    except ValueError:
        messages.error(request, 'El handicap debe ser un número válido.')
        return redirect('jugadores')

    try:
        puntos = float(request.POST.get('puntos', 0) or 0)
    except (ValueError, TypeError):
        puntos = 0
    try:
        cn_totales = int(float(request.POST.get('cn_totales', 0) or 0))
    except (ValueError, TypeError):
        cn_totales = 0
    categoria = request.POST.get('categoria', '').strip()

    es_director = request.POST.get('es_director') == '1'

    jugador.nombre = nombre
    jugador.apellido = apellido
    jugador.handicap = handicap
    jugador.puntos = puntos
    jugador.cn_totales = cn_totales
    jugador.categoria = categoria
    jugador.es_director = es_director
    jugador.save()

    messages.success(request, f'Jugador {jugador.nombre_completo} actualizado.')
    return redirect('jugadores')


def jugador_eliminar(request, id):
    """Eliminar (desactivar) un jugador."""
    if request.method != 'POST':
        return redirect('jugadores')
    
    jugador = get_object_or_404(Jugador, id=id)
    jugador.activo = False
    jugador.save()

    messages.warning(request, f'Jugador {jugador.nombre_completo} eliminado.')
    return redirect('jugadores')


def jugadores_eliminar_todos(request):
    """Eliminar todos los jugadores de la base de datos."""
    if request.method != 'POST':
        return redirect('jugadores')
    
    total = Jugador.objects.filter(activo=True).count()

    if total == 0:
        messages.info(request, 'No hay jugadores para eliminar.')
        return redirect('jugadores')

    # Eliminar todas las parejas de torneo
    ParejaTorneo.objects.all().delete()
    # Resetear estado de todos los torneos
    Torneo.objects.update(estado='configuracion')
    # Eliminar todos los jugadores
    Jugador.objects.all().delete()

    messages.warning(request, f'Se eliminaron {total} jugadores de la base de datos.')
    return redirect('jugadores')


def jugadores_importar(request):
    """Importar jugadores desde un archivo CSV."""
    if request.method != 'POST':
        return redirect('jugadores')
    
    archivo = request.FILES.get('archivo_csv')

    if not archivo or not archivo.name.endswith('.csv'):
        messages.error(request, 'Por favor, seleccioná un archivo CSV válido.')
        return redirect('jugadores')

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
            existente = Jugador.objects.filter(
                nombre=nombre, apellido=apellido, activo=True
            ).first()

            if existente:
                existente.handicap = handicap
                existente.puntos = puntos
                existente.cn_totales = cn_totales
                existente.categoria = categoria
                existente.save()
            else:
                jugador = Jugador(
                    nombre=nombre, apellido=apellido, handicap=handicap,
                    puntos=puntos, cn_totales=cn_totales, categoria=categoria,
                )
                jugador.save()

            count += 1

        messages.success(request, f'Se importaron/actualizaron {count} jugadores exitosamente.')
    except Exception as e:
        messages.error(request, f'Error al importar el archivo: {str(e)}')

    return redirect('jugadores')


def api_buscar_jugadores(request):
    """API para buscar jugadores por nombre o apellido (usado en autocompletado)."""
    query = request.GET.get('q', '').strip()
    torneo_id = request.GET.get('torneo_id')
    excluir_ids = request.GET.getlist('excluir')  # IDs a excluir (ya seleccionados)
    
    if len(query) < 1:
        return JsonResponse({'jugadores': []})
    
    # Buscar jugadores activos que coincidan
    jugadores = Jugador.objects.filter(activo=True).filter(
        Q(nombre__icontains=query) | Q(apellido__icontains=query)
    ).order_by('apellido', 'nombre')[:15]
    
    # Si hay un torneo, excluir jugadores ya en parejas de ese torneo
    if torneo_id:
        try:
            torneo = Torneo.objects.get(id=torneo_id)
            ids_en_parejas = set()
            for pareja in torneo.parejas.all():
                ids_en_parejas.add(pareja.jugador1_id)
                ids_en_parejas.add(pareja.jugador2_id)
            jugadores = [j for j in jugadores if j.id not in ids_en_parejas]
        except Torneo.DoesNotExist:
            pass
    
    # Excluir IDs específicos (jugador ya seleccionado en el otro campo)
    if excluir_ids:
        excluir_set = set(int(i) for i in excluir_ids if i.isdigit())
        jugadores = [j for j in jugadores if j.id not in excluir_set]
    
    resultado = [{
        'id': j.id,
        'nombre': j.nombre,
        'apellido': j.apellido,
        'handicap': float(j.handicap),
    } for j in jugadores[:10]]
    
    return JsonResponse({'jugadores': resultado})


# =============================================================================
# FUNCIONES AUXILIARES PARA CARGA DE BASE
# =============================================================================

_NOMBRES_NOMBRE = {'nombre', 'name', 'primer nombre', 'first name', 'first_name', 'nombres'}
_NOMBRES_APELLIDO = {'apellido', 'surname', 'last name', 'last_name', 'apellidos'}
_NOMBRES_HANDICAP = {'handicap', 'hcp', 'hc', 'hdcp', 'hándicap'}
_NOMBRES_PUNTOS = {'puntos', 'points', 'pts', 'puntaje', 'score', 'puntos ranking',
                   'puntos_ranking', 'ranking', 'puntos totales', 'puntos_totales',
                   'pts.', 'ptos', 'ptos.', 'puntos aub'}
_NOMBRES_CN = {'cn totales', 'cn_totales', 'cn', 'campeonatos', 'campeonatos nacionales',
               'nacionales', 'cn totals', 'cn total'}
_NOMBRES_CATEGORIA = {'categoria', 'categoría', 'category', 'cat', 'nivel', 'level'}


def _detectar_columnas(headers):
    """Detecta qué columna es cada campo por los nombres de cabecera."""
    # Normalizar headers: minúsculas, sin espacios extra, sin caracteres invisibles
    headers_lower = []
    for h in headers:
        h_norm = str(h).lower().replace('\xa0', ' ').replace('\u200b', '').strip()
        # Remover puntos finales y espacios múltiples
        h_norm = ' '.join(h_norm.split())
        h_norm = h_norm.rstrip('.')
        headers_lower.append(h_norm)
    
    cols = {
        'col_nombre': None, 'col_apellido': None, 'col_handicap': None,
        'col_puntos': None, 'col_cn': None, 'col_categoria': None,
    }

    for i, h in enumerate(headers_lower):
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

    # Segunda pasada: coincidencia parcial (los headers ya están normalizados)
    for i, h in enumerate(headers_lower):
        # Saltar columnas ya asignadas
        cols_asignadas = {cols['col_nombre'], cols['col_apellido'], cols['col_handicap'],
                         cols['col_puntos'], cols['col_cn'], cols['col_categoria']}
        if i in cols_asignadas:
            continue
        if cols['col_puntos'] is None and ('punto' in h or 'point' in h or 'pts' in h or 'ptos' in h or 'score' in h or 'ranking' in h):
            cols['col_puntos'] = i
        elif cols['col_cn'] is None and ('cn' in h or 'campeonato' in h or 'nacional' in h):
            cols['col_cn'] = i
        elif cols['col_categoria'] is None and ('categ' in h or 'nivel' in h or 'level' in h):
            cols['col_categoria'] = i
        elif cols['col_handicap'] is None and ('hcp' in h or 'handicap' in h or 'hándicap' in h):
            cols['col_handicap'] = i

    cols['nombre_combinado'] = cols['col_nombre'] is not None and cols['col_apellido'] is None
    return cols


def _separar_apellido_nombre(valor):
    """Separa un string 'Apellido Nombre' en (nombre, apellido)."""
    valor = valor.strip()
    if not valor:
        return '', ''

    if ',' in valor:
        partes = valor.split(',', 1)
        apellido = partes[0].strip()
        nombre = partes[1].strip() if len(partes) > 1 else ''
        return nombre, apellido

    partes = valor.split()
    if len(partes) == 1:
        return valor, ''
    elif len(partes) == 2:
        return partes[1], partes[0]
    else:
        nombre = partes[-1]
        apellido = ' '.join(partes[:-1])
        return nombre, apellido


def _extraer_campo_float(fila, col_idx):
    """Extrae un valor float de una fila."""
    if col_idx is None or col_idx >= len(fila):
        return 0
    val = str(fila[col_idx]).strip().replace(',', '.')
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0


def _extraer_campo_int(fila, col_idx):
    """Extrae un valor entero de una fila."""
    if col_idx is None or col_idx >= len(fila):
        return 0
    val = str(fila[col_idx]).strip().replace(',', '.').replace('.0', '')
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return 0


def _extraer_campo_str(fila, col_idx):
    """Extrae un valor string de una fila."""
    if col_idx is None or col_idx >= len(fila):
        return ''
    val = str(fila[col_idx]).strip()
    return '' if val == 'None' else val


def _encontrar_fila_header(filas, max_buscar=10):
    """Busca la fila que contiene los encabezados."""
    for idx in range(min(max_buscar, len(filas))):
        cols = _detectar_columnas(filas[idx])
        if cols['col_nombre'] is not None and cols['col_handicap'] is not None:
            return idx, cols
        if cols['col_nombre'] is not None:
            return idx, cols
    return None, None


def _parsear_filas(filas):
    """Parsea filas genéricas y devuelve lista de dicts."""
    if not filas:
        return []

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
        existente = Jugador.objects.filter(
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


def cargar_base(request):
    """Página para cargar la base de datos histórica de handicaps."""
    if request.method == 'GET':
        return render(request, 'cargar_base.html')

    # POST: procesar archivo subido
    archivo = request.FILES.get('archivo')

    if not archivo or not archivo.name:
        messages.error(request, 'Por favor, seleccioná un archivo.')
        return redirect('cargar_base')

    filename = archivo.name.lower()
    archivo_bytes = archivo.read()

    try:
        if filename.endswith('.csv') or filename.endswith('.txt'):
            datos = _parsear_csv(archivo_bytes)
        elif filename.endswith('.xlsx'):
            datos = _parsear_excel(archivo_bytes)
        else:
            messages.error(request, 'Formato no soportado. Usá archivos .csv o .xlsx')
            return redirect('cargar_base')
    except Exception as e:
        messages.error(request, f'Error al leer el archivo: {str(e)}')
        return redirect('cargar_base')

    if not datos:
        messages.warning(request, 'No se encontraron datos válidos en el archivo. '
              'Verificá que tenga columnas: Nombre, Apellido, Handicap.')
        return redirect('cargar_base')

    # Generar preview
    preview, nuevos, actualizados, sin_cambios = _generar_preview(datos)

    # Codificar datos para el form de confirmación
    datos_json = json.dumps(datos)

    return render(request, 'cargar_base.html', {
        'preview': preview,
        'datos_json': datos_json,
        'nuevos': nuevos,
        'actualizados': actualizados,
        'sin_cambios': sin_cambios,
        'total': len(preview),
    })


def cargar_base_confirmar(request):
    """Confirma e importa los datos de la vista previa."""
    if request.method != 'POST':
        return redirect('cargar_base')
    
    datos_json = request.POST.get('datos_json', '[]')

    try:
        datos = json.loads(datos_json)
    except (json.JSONDecodeError, ValueError):
        messages.error(request, 'Error al procesar los datos. Intentá subir el archivo de nuevo.')
        return redirect('cargar_base')

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

        existente = Jugador.objects.filter(
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
                existente.save()
                actualizados += 1
        else:
            jugador = Jugador(
                nombre=nombre, apellido=apellido, handicap=handicap,
                puntos=puntos, cn_totales=cn_totales, categoria=categoria,
            )
            jugador.save()
            nuevos += 1

    messages.success(request,
        f'Base de handicaps importada exitosamente: '
        f'{nuevos} jugadores nuevos, {actualizados} handicaps actualizados.'
    )
    return redirect('jugadores')


# =============================================================================
# VISTAS DE TORNEOS
# =============================================================================

def torneos(request):
    """Lista de torneos."""
    lista = Torneo.objects.order_by('-fecha')
    return render(request, 'torneos.html', {'torneos': lista})


def torneo_nuevo(request):
    """Crear un nuevo torneo."""
    if request.method == 'POST':
        nombre = request.POST.get('nombre', '').strip()
        fecha_str = request.POST.get('fecha', '')
        director_id = request.POST.get('director', '').strip()
        lugar_id = request.POST.get('lugar', '').strip()

        if not nombre:
            messages.error(request, 'El nombre del torneo es obligatorio.')
            return redirect('torneo_nuevo')

        try:
            fecha = date.fromisoformat(fecha_str) if fecha_str else date.today()
        except ValueError:
            fecha = date.today()

        torneo = Torneo(nombre=nombre, fecha=fecha)

        # Asignar director si se seleccionó
        if director_id:
            try:
                torneo.director = Jugador.objects.get(id=int(director_id), es_director=True)
            except (Jugador.DoesNotExist, ValueError):
                pass

        # Asignar lugar si se seleccionó
        if lugar_id:
            try:
                torneo.lugar = Lugar.objects.get(id=int(lugar_id))
            except (Lugar.DoesNotExist, ValueError):
                pass

        torneo.save()

        messages.success(request, f'Torneo "{torneo.nombre}" creado exitosamente.')
        # Redirigir a la página de acciones del torneo
        return redirect('torneo_acciones', id=torneo.id)

    # GET: mostrar formulario con directores autorizados y lugares
    directores = Jugador.objects.filter(activo=True, es_director=True).order_by('apellido', 'nombre')
    lugares = Lugar.objects.filter(activo=True)

    return render(request, 'torneo_nuevo.html', {
        'hoy': date.today().isoformat(),
        'directores': directores,
        'lugares': lugares,
    })


def torneo_acciones(request, id):
    """Página principal (hub) del torneo: acciones e información de resultados."""
    torneo = get_object_or_404(Torneo, id=id)
    
    # Verificar si hay resultados importados
    rankings = None
    resultado = None
    total_boards = 0
    pendiente_revision = False
    total_parejas = torneo.cantidad_parejas
    try:
        resultado = torneo.resultado_importado
        total_boards = resultado.manos.values('board_numero').distinct().count()
        # Usar la cantidad de rankings importados si hay resultado
        total_parejas = resultado.rankings.count()
        if resultado.confirmado:
            rankings = resultado.rankings.all()
        else:
            pendiente_revision = True
    except ResultadoImportado.DoesNotExist:
        pass
    
    return render(request, 'torneo_acciones.html', {
        'torneo': torneo,
        'tipos_torneo': TIPOS_TORNEO,
        'resultado': resultado,
        'rankings': rankings,
        'total_boards': total_boards,
        'total_parejas': total_parejas,
        'pendiente_revision': pendiente_revision,
    })


def torneo_detalle(request, id):
    """Detalle del torneo: configuración de parejas y resultados."""
    torneo = get_object_or_404(Torneo, id=id)

    # Obtener IDs de jugadores ya asignados a alguna pareja en este torneo
    jugadores_en_parejas_ids = set()
    for pareja in torneo.parejas.all():
        jugadores_en_parejas_ids.add(pareja.jugador1_id)
        jugadores_en_parejas_ids.add(pareja.jugador2_id)

    # Jugadores disponibles (activos y NO asignados a parejas en este torneo)
    jugadores_disponibles = Jugador.objects.filter(activo=True).exclude(
        id__in=jugadores_en_parejas_ids
    ).order_by('apellido', 'nombre')

    return render(request, 'torneo_detalle.html', {
        'torneo': torneo,
        'jugadores_disponibles': jugadores_disponibles,
        'tipos_torneo': TIPOS_TORNEO,
        'tablas_puntos': TABLAS_PUNTOS,
    })


def torneo_agregar_pareja(request, id):
    """Agregar una pareja al torneo."""
    if request.method != 'POST':
        return redirect('torneo_detalle', id=id)
    
    torneo = get_object_or_404(Torneo, id=id)

    try:
        jugador1_id = int(request.POST.get('jugador1_id', 0))
        jugador2_id = int(request.POST.get('jugador2_id', 0))
    except (ValueError, TypeError):
        jugador1_id = 0
        jugador2_id = 0

    if not jugador1_id or not jugador2_id:
        messages.error(request, 'Debés seleccionar dos jugadores para la pareja.')
        return redirect('torneo_detalle', id=id)

    if jugador1_id == jugador2_id:
        messages.error(request, 'Los dos jugadores de la pareja deben ser diferentes.')
        return redirect('torneo_detalle', id=id)

    # Verificar que los jugadores no estén ya en otra pareja del torneo
    existente = ParejaTorneo.objects.filter(torneo_id=id).filter(
        Q(jugador1_id__in=[jugador1_id, jugador2_id]) |
        Q(jugador2_id__in=[jugador1_id, jugador2_id])
    ).first()

    if existente:
        messages.error(request, 'Uno o ambos jugadores ya están asignados a otra pareja en este torneo.')
        return redirect('torneo_detalle', id=id)

    jugador1 = get_object_or_404(Jugador, id=jugador1_id)
    jugador2 = get_object_or_404(Jugador, id=jugador2_id)

    pareja = ParejaTorneo(
        torneo=torneo,
        jugador1=jugador1,
        jugador2=jugador2,
        handicap_pareja=round((jugador1.handicap + jugador2.handicap) / 2, 2)
    )
    pareja.save()

    # Si el torneo estaba equilibrado, resetear
    if torneo.estado == 'equilibrado':
        torneo.estado = 'configuracion'
        torneo.save()
        for p in torneo.parejas.all():
            p.direccion = None
            p.save()

    messages.success(request, f'Pareja {jugador1.nombre_completo} & {jugador2.nombre_completo} agregada.')
    return redirect('torneo_detalle', id=id)


def torneo_eliminar_pareja(request, id, pareja_id):
    """Eliminar una pareja del torneo."""
    if request.method != 'POST':
        return redirect('torneo_detalle', id=id)
    
    pareja = get_object_or_404(ParejaTorneo, id=pareja_id)

    if pareja.torneo_id != id:
        messages.error(request, 'La pareja no pertenece a este torneo.')
        return redirect('torneo_detalle', id=id)

    torneo = get_object_or_404(Torneo, id=id)

    # Si el torneo estaba equilibrado, resetear
    if torneo.estado == 'equilibrado':
        torneo.estado = 'configuracion'
        torneo.save()
        for p in torneo.parejas.all():
            p.direccion = None
            p.save()

    pareja.delete()

    messages.warning(request, 'Pareja eliminada del torneo.')
    return redirect('torneo_detalle', id=id)


def torneo_equilibrar(request, id):
    """Ejecutar el algoritmo de equilibrado."""
    if request.method != 'POST':
        return redirect('torneo_detalle', id=id)
    
    torneo = get_object_or_404(Torneo, id=id)

    if torneo.parejas.count() < 2:
        messages.error(request, 'Se necesitan al menos 2 parejas para equilibrar el torneo.')
        return redirect('torneo_detalle', id=id)

    # Preparar datos para el algoritmo
    datos_parejas = [
        {'id': p.id, 'handicap_pareja': p.handicap_pareja}
        for p in torneo.parejas.all()
    ]

    # Ejecutar el equilibrado
    resultado = equilibrar_parejas(datos_parejas)

    # Asignar direcciones
    ns_ids = {p['id'] for p in resultado['ns']}
    eo_ids = {p['id'] for p in resultado['eo']}

    for pareja in torneo.parejas.all():
        if pareja.id in ns_ids:
            pareja.direccion = 'NS'
        elif pareja.id in eo_ids:
            pareja.direccion = 'EO'
        pareja.save()

    torneo.estado = 'equilibrado'
    torneo.save()

    diferencia = resultado['diferencia']
    messages.success(request,
        f'Torneo equilibrado exitosamente. '
        f'Promedio NS: {resultado["ns_promedio"]} | '
        f'Promedio EO: {resultado["eo_promedio"]} | '
        f'Diferencia: {diferencia}'
    )
    return redirect('torneo_detalle', id=id)


def torneo_reset(request, id):
    """Resetear el equilibrado del torneo."""
    if request.method != 'POST':
        return redirect('torneo_detalle', id=id)
    
    torneo = get_object_or_404(Torneo, id=id)
    torneo.estado = 'configuracion'
    torneo.save()

    for pareja in torneo.parejas.all():
        pareja.direccion = None
        pareja.save()

    messages.info(request, 'Equilibrado reseteado. Podés volver a equilibrar.')
    return redirect('torneo_acciones', id=id)


def torneo_resultados(request, id):
    """Guardar posiciones finales, porcentajes y calcular puntos de ranking."""
    if request.method != 'POST':
        return redirect('torneo_detalle', id=id)
    
    torneo = get_object_or_404(Torneo, id=id)

    if torneo.estado != 'equilibrado':
        messages.error(request, 'El torneo debe estar equilibrado para asignar resultados.')
        return redirect('torneo_detalle', id=id)

    # Guardar tipo de torneo
    tipo = request.POST.get('tipo_torneo', 'handicap')
    torneo.tipo = tipo
    torneo.save()

    tabla = TABLAS_PUNTOS.get(tipo, [])

    # Guardar posiciones, porcentajes y calcular puntos para cada pareja
    for pareja in torneo.parejas.all():
        pos_str = request.POST.get(f'pos_{pareja.id}', '').strip()
        pct_str = request.POST.get(f'pct_{pareja.id}', '').strip()

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
                    if pos <= 4:
                        if pct >= 58:
                            pareja.puntos_ranking = math.ceil(pct - 50)
                        elif pct >= 50:
                            if pos <= len(tabla):
                                pareja.puntos_ranking = tabla[pos - 1]
                            else:
                                pareja.puntos_ranking = 0
                        else:
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

        pareja.save()

    messages.success(request, 'Resultados guardados exitosamente.')
    return redirect('torneo_acciones', id=id)


def torneo_eliminar(request, id):
    """Eliminar un torneo."""
    if request.method != 'POST':
        return redirect('torneos')
    
    torneo = get_object_or_404(Torneo, id=id)
    nombre = torneo.nombre
    torneo.delete()

    messages.warning(request, f'Torneo "{nombre}" eliminado.')
    return redirect('torneos')


# =============================================================================
# RANKING ANUAL
# =============================================================================

def ranking(request, anio=None):
    """Ranking anual de jugadores basado en puntos acumulados en torneos."""
    if anio is None:
        anio = date.today().year

    # Años disponibles
    anios_disponibles = list(
        Torneo.objects.annotate(anio=ExtractYear('fecha'))
        .values_list('anio', flat=True)
        .distinct()
        .order_by('-anio')
    )

    if anio not in anios_disponibles and anios_disponibles:
        anio = anios_disponibles[0]

    # Obtener todos los torneos del año seleccionado
    torneos_anio = Torneo.objects.filter(
        fecha__year=anio,
    ).order_by('-fecha')

    # Acumular puntos por jugador
    puntos_jugador = {}

    for torneo_obj in torneos_anio:
        tipo_label = TIPOS_TORNEO.get(torneo_obj.tipo, torneo_obj.tipo or '')

        # Fuente 1: Resultados importados confirmados (RankingImportado)
        try:
            resultado = torneo_obj.resultado_importado
            if resultado.confirmado:
                for ri in resultado.rankings.all():
                    pts = ri.puntos_asignados or 0
                    if pts <= 0:
                        continue

                    for jugador in [ri.jugador1, ri.jugador2]:
                        if jugador is None:
                            continue
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
                            'torneo': torneo_obj.nombre,
                            'fecha': torneo_obj.fecha,
                            'tipo': tipo_label,
                            'posicion': ri.posicion,
                            'direccion': '',
                            'puntos': pts,
                        })
                # Si ya tiene resultados importados confirmados, no sumar también las parejas manuales
                continue
        except ResultadoImportado.DoesNotExist:
            pass

        # Fuente 2: Parejas del equilibrador manual (ParejaTorneo)
        if torneo_obj.estado != 'equilibrado':
            continue

        for pareja in torneo_obj.parejas.all():
            if not pareja.puntos_ranking or pareja.puntos_ranking <= 0:
                continue

            pts = pareja.puntos_ranking

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
                    'torneo': torneo_obj.nombre,
                    'fecha': torneo_obj.fecha,
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

    return render(request, 'ranking.html', {
        'ranking': ranking_list,
        'anio': anio,
        'anios_disponibles': anios_disponibles,
        'total_torneos': len(torneos_anio),
    })


# =============================================================================
# IMPORTACIÓN DE RESULTADOS DE TORNEO
# =============================================================================

def torneo_importar_archivos(request, id):
    """Importar archivos desde la página de acciones del torneo.
    
    Maneja dos flujos:
    - Importar Resultados (Ranks.txt): crea resultado nuevo con rankings
    - Importar Travellers (Travellers.txt): agrega manos a un resultado existente
    """
    if request.method != 'POST':
        return redirect('torneo_acciones', id=id)
    
    torneo = get_object_or_404(Torneo, id=id)
    archivo_ranks = request.FILES.get('archivo_ranks')
    archivo_travellers = request.FILES.get('archivo_travellers')
    
    # Si hay archivo de ranks, usar el flujo completo de importación
    if archivo_ranks and archivo_ranks.name:
        return torneo_importar_resultados(request, id)
    
    # Si solo hay travellers, importar manos sobre resultado existente
    if archivo_travellers and archivo_travellers.name:
        try:
            resultado = torneo.resultado_importado
        except ResultadoImportado.DoesNotExist:
            messages.error(request,
                'Primero debés importar los Resultados (Ranks.txt) antes de importar Travellers.'
            )
            return redirect('torneo_acciones', id=id)
        
        try:
            archivo_bytes = archivo_travellers.read()
            contenido = None
            for encoding in ('utf-8-sig', 'utf-8', 'latin-1', 'cp1252'):
                try:
                    contenido = archivo_bytes.decode(encoding)
                    break
                except UnicodeDecodeError:
                    continue
            if contenido is None:
                contenido = archivo_bytes.decode('utf-8', errors='replace')
            
            datos_travellers = parsear_travellers(contenido)
            
            if not datos_travellers or not datos_travellers.get('manos'):
                messages.error(request, 'No se encontraron manos en el archivo Travellers.')
                return redirect('torneo_acciones', id=id)
            
            # Eliminar manos anteriores y cargar nuevas
            resultado.manos.all().delete()
            resultado.nombre_archivo_travellers = archivo_travellers.name
            resultado.save()
            
            manos_bulk = []
            for m in datos_travellers['manos']:
                manos_bulk.append(ManoJugada(
                    resultado=resultado,
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
                ))
            ManoJugada.objects.bulk_create(manos_bulk)
            
            messages.success(request,
                f'Travellers importados exitosamente: {len(manos_bulk)} manos cargadas.'
            )
            return redirect('torneo_acciones', id=id)
            
        except Exception as e:
            messages.error(request, f'Error al importar Travellers: {str(e)}')
            return redirect('torneo_acciones', id=id)
    
    messages.error(request, 'No se seleccionó ningún archivo.')
    return redirect('torneo_acciones', id=id)


def torneo_importar_resultados(request, id):
    """Importar resultados de torneo desde archivos Ranks.txt y Travellers.txt."""
    torneo = get_object_or_404(Torneo, id=id)
    
    if request.method == 'GET':
        return render(request, 'importar_resultados.html', {
            'torneo': torneo,
            'tipos_torneo': TIPOS_TORNEO,
        })
    
    # POST: procesar archivos subidos
    archivo_ranks = request.FILES.get('archivo_ranks')
    archivo_travellers = request.FILES.get('archivo_travellers')
    tipo_torneo = request.POST.get('tipo_torneo', 'handicap')
    
    if not archivo_ranks or not archivo_ranks.name:
        messages.error(request, 'El archivo de Rankings es obligatorio.')
        return redirect('torneo_acciones', id=id)
    
    try:
        # Leer archivos (probar diferentes codificaciones)
        archivo_bytes_ranks = archivo_ranks.read()
        for encoding in ('utf-8-sig', 'utf-8', 'latin-1', 'cp1252'):
            try:
                contenido_ranks = archivo_bytes_ranks.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        else:
            contenido_ranks = archivo_bytes_ranks.decode('utf-8', errors='replace')
        
        contenido_travellers = None
        if archivo_travellers and archivo_travellers.name:
            archivo_bytes_travellers = archivo_travellers.read()
            for encoding in ('utf-8-sig', 'utf-8', 'latin-1', 'cp1252'):
                try:
                    contenido_travellers = archivo_bytes_travellers.decode(encoding)
                    break
                except UnicodeDecodeError:
                    continue
            else:
                contenido_travellers = archivo_bytes_travellers.decode('utf-8', errors='replace')
        
        # Parsear archivos
        datos_ranks = parsear_ranks(contenido_ranks)
        datos_travellers = parsear_travellers(contenido_travellers) if contenido_travellers else None
        
        if not datos_ranks['rankings']:
            messages.error(request, 'No se encontraron rankings en el archivo.')
            return redirect('torneo_acciones', id=id)
        
        # Eliminar resultado importado anterior si existe
        ResultadoImportado.objects.filter(torneo_id=id).delete()
        
        # Crear nuevo resultado importado
        resultado = ResultadoImportado(
            torneo=torneo,
            nombre_archivo_ranks=archivo_ranks.name,
            nombre_archivo_travellers=archivo_travellers.name if archivo_travellers else None,
            session_info=datos_ranks.get('session', ''),
            mesas=datos_ranks.get('mesas'),
            boards_totales=datos_ranks.get('boards'),
            movimiento=datos_ranks.get('movimiento', '')
        )
        resultado.save()
        
        # Obtener todos los jugadores para emparejar
        jugadores_db = list(Jugador.objects.filter(activo=True))
        
        # Guardar rankings
        for r in datos_ranks['rankings']:
            puntos = calcular_puntos_ranking(
                r['posicion'], 
                r['porcentaje_con_handicap'], 
                tipo_torneo
            )
            
            ranking = RankingImportado(
                resultado=resultado,
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
            ranking.save()
        
        # Guardar manos jugadas si hay archivo de travellers
        if datos_travellers and datos_travellers['manos']:
            manos_bulk = []
            for m in datos_travellers['manos']:
                mano = ManoJugada(
                    resultado=resultado,
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
                manos_bulk.append(mano)
            ManoJugada.objects.bulk_create(manos_bulk)
        
        # Actualizar tipo de torneo
        torneo.tipo = tipo_torneo
        torneo.estado = 'equilibrado'
        torneo.save()
        
        total_rankings = len(datos_ranks['rankings'])
        total_manos = len(datos_travellers['manos']) if datos_travellers else 0
        
        messages.success(request,
            f'Resultados importados: {total_rankings} parejas, {total_manos} manos. Revisá y confirmá los datos.'
        )
        return redirect('torneo_revisar_resultados', id=id)
        
    except Exception as e:
        messages.error(request, f'Error al importar los archivos: {str(e)}')
        return redirect('torneo_acciones', id=id)


def torneo_revisar_resultados(request, id):
    """Página de revisión y edición manual de resultados importados antes de confirmar."""
    torneo = get_object_or_404(Torneo, id=id)
    
    try:
        resultado = torneo.resultado_importado
    except ResultadoImportado.DoesNotExist:
        messages.warning(request, 'No hay resultados importados para revisar.')
        return redirect('torneo_acciones', id=id)
    
    rankings = resultado.rankings.all()
    ranking_ids = ','.join(str(r.id) for r in rankings)
    
    return render(request, 'torneo_revisar_resultados.html', {
        'torneo': torneo,
        'resultado': resultado,
        'rankings': rankings,
        'ranking_ids': ranking_ids,
        'tipos_torneo': TIPOS_TORNEO,
    })


def torneo_confirmar_resultados(request, id):
    """Guardar ediciones manuales y confirmar los resultados del torneo."""
    if request.method != 'POST':
        return redirect('torneo_revisar_resultados', id=id)
    
    torneo = get_object_or_404(Torneo, id=id)
    
    try:
        resultado = torneo.resultado_importado
    except ResultadoImportado.DoesNotExist:
        messages.error(request, 'No hay resultados importados para confirmar.')
        return redirect('torneo_acciones', id=id)
    
    tipo_torneo = request.POST.get('tipo_torneo', torneo.tipo or 'handicap')
    ranking_ids_str = request.POST.get('ranking_ids', '')
    deleted_ids_str = request.POST.get('deleted_ids', '')
    
    # IDs a eliminar
    deleted_ids = set()
    if deleted_ids_str:
        deleted_ids = {int(x) for x in deleted_ids_str.split(',') if x.strip()}
    
    # Eliminar rankings descartados
    if deleted_ids:
        RankingImportado.objects.filter(id__in=deleted_ids, resultado=resultado).delete()
    
    # Actualizar cada ranking con los valores editados
    jugadores_db = list(Jugador.objects.filter(activo=True))
    
    ranking_ids = [int(x) for x in ranking_ids_str.split(',') if x.strip()]
    for rid in ranking_ids:
        if rid in deleted_ids:
            continue
        
        try:
            ranking = RankingImportado.objects.get(id=rid, resultado=resultado)
        except RankingImportado.DoesNotExist:
            continue
        
        # Leer valores del formulario
        ranking.posicion = int(request.POST.get(f'posicion_{rid}', ranking.posicion) or ranking.posicion)
        ranking.numero_pareja = int(request.POST.get(f'numero_pareja_{rid}', ranking.numero_pareja) or ranking.numero_pareja)
        
        nuevo_j1 = request.POST.get(f'nombre_jugador1_{rid}', ranking.nombre_jugador1)
        nuevo_j2 = request.POST.get(f'nombre_jugador2_{rid}', ranking.nombre_jugador2)
        
        # Re-emparejar si cambió el nombre
        if nuevo_j1 != ranking.nombre_jugador1:
            ranking.nombre_jugador1 = nuevo_j1
            ranking.jugador1_id = emparejar_jugadores(nuevo_j1, jugadores_db)
        if nuevo_j2 != ranking.nombre_jugador2:
            ranking.nombre_jugador2 = nuevo_j2
            ranking.jugador2_id = emparejar_jugadores(nuevo_j2, jugadores_db)
        
        ranking.boards_jugados = int(request.POST.get(f'boards_jugados_{rid}', ranking.boards_jugados) or 0)
        
        try:
            ranking.porcentaje = float(request.POST.get(f'porcentaje_{rid}', ranking.porcentaje) or 0)
        except (ValueError, TypeError):
            pass
        try:
            ranking.handicap = float(request.POST.get(f'handicap_{rid}', ranking.handicap) or 0)
        except (ValueError, TypeError):
            pass
        try:
            ranking.porcentaje_con_handicap = float(request.POST.get(f'porcentaje_con_handicap_{rid}', ranking.porcentaje_con_handicap) or 0)
        except (ValueError, TypeError):
            pass
        try:
            ranking.puntos_asignados = float(request.POST.get(f'puntos_asignados_{rid}', ranking.puntos_asignados) or 0)
        except (ValueError, TypeError):
            pass
        
        # Recalcular puntos si se cambió el tipo de torneo
        ranking.puntos_asignados = calcular_puntos_ranking(
            ranking.posicion,
            ranking.porcentaje_con_handicap,
            tipo_torneo
        )
        
        ranking.save()
    
    # Marcar como confirmado
    resultado.confirmado = True
    resultado.save()
    
    # Actualizar tipo de torneo
    torneo.tipo = tipo_torneo
    torneo.save()
    
    # Contar jugadores vinculados para el mensaje
    jugadores_vinculados = 0
    for ranking in resultado.rankings.all():
        if ranking.jugador1:
            jugadores_vinculados += 1
        if ranking.jugador2:
            jugadores_vinculados += 1
    
    messages.success(request,
        f'Resultados confirmados. {jugadores_vinculados} jugadores vinculados al ranking.'
    )
    return redirect('torneo_acciones', id=id)


def torneo_ver_resultados(request, id):
    """Ver los resultados importados de un torneo."""
    torneo = get_object_or_404(Torneo, id=id)
    
    try:
        resultado = torneo.resultado_importado
    except ResultadoImportado.DoesNotExist:
        messages.warning(request, 'No hay resultados importados para este torneo.')
        return redirect('torneo_acciones', id=id)
    
    # Obtener rankings ordenados por posición
    rankings = resultado.rankings.all()
    
    # Obtener estadísticas de manos
    total_boards = resultado.manos.values('board_numero').distinct().count()
    
    return render(request, 'ver_resultados.html', {
        'torneo': torneo,
        'resultado': resultado,
        'rankings': rankings,
        'total_boards': total_boards,
        'tipos_torneo': TIPOS_TORNEO,
    })


def torneo_ver_manos(request, id, board=None):
    """Ver las manos jugadas en un torneo."""
    torneo = get_object_or_404(Torneo, id=id)
    
    try:
        resultado = torneo.resultado_importado
    except ResultadoImportado.DoesNotExist:
        messages.warning(request, 'No hay resultados importados para este torneo.')
        return redirect('torneo_acciones', id=id)
    
    # Obtener lista de boards disponibles
    boards_disponibles = list(
        resultado.manos.values_list('board_numero', flat=True)
        .distinct()
        .order_by('board_numero')
    )
    
    if not boards_disponibles:
        messages.warning(request, 'No hay manos registradas para este torneo.')
        return redirect('torneo_acciones', id=id)
    
    # Si no se especifica board, mostrar el primero
    if board is None:
        board = boards_disponibles[0]
    
    # Obtener manos del board seleccionado
    manos = resultado.manos.filter(board_numero=board).order_by('-mp_ns')
    
    return render(request, 'ver_manos.html', {
        'torneo': torneo,
        'resultado': resultado,
        'board_actual': board,
        'boards_disponibles': boards_disponibles,
        'manos': manos,
    })


def torneo_actualizar_puntos(request, id):
    """Actualiza los puntos de ranking de los jugadores basándose en los resultados importados."""
    if request.method != 'POST':
        return redirect('torneo_ver_resultados', id=id)
    
    torneo = get_object_or_404(Torneo, id=id)
    
    try:
        resultado = torneo.resultado_importado
    except ResultadoImportado.DoesNotExist:
        messages.error(request, 'No hay resultados importados para este torneo.')
        return redirect('torneo_acciones', id=id)
    
    rankings = resultado.rankings.all()
    
    jugadores_actualizados = 0
    
    for ranking in rankings:
        puntos = ranking.puntos_asignados or 0
        
        if puntos > 0:
            # Actualizar jugador 1 si está vinculado
            if ranking.jugador1:
                ranking.jugador1.puntos = (ranking.jugador1.puntos or 0) + puntos
                ranking.jugador1.save()
                jugadores_actualizados += 1
            
            # Actualizar jugador 2 si está vinculado
            if ranking.jugador2:
                ranking.jugador2.puntos = (ranking.jugador2.puntos or 0) + puntos
                ranking.jugador2.save()
                jugadores_actualizados += 1
    
    messages.success(request, f'Se actualizaron los puntos de {jugadores_actualizados} jugadores.')
    return redirect('torneo_acciones', id=id)

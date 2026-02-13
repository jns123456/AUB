"""
Parsers para archivos de resultados de torneos de bridge.

Soporta los formatos de PairsScorer:
- Ranks.txt: Rankings finales del torneo
- Travellers.txt: Detalle de cada mano/board jugada
"""

import re
from typing import Dict, List, Optional, Tuple


def _limpiar_texto(texto: str) -> str:
    """Limpia un texto de espacios extra y caracteres invisibles."""
    return texto.strip().replace('\xa0', ' ').replace('\u200b', '')


def _parsear_nombres_pareja(texto: str) -> Tuple[str, str]:
    """
    Separa los nombres de una pareja del formato "Nombre1 Apellido1 & Nombre2 Apellido2".
    
    Returns:
        Tuple con (nombre_jugador1, nombre_jugador2)
    """
    texto = _limpiar_texto(texto)
    if '&' in texto:
        partes = texto.split('&')
        return _limpiar_texto(partes[0]), _limpiar_texto(partes[1]) if len(partes) > 1 else ''
    return texto, ''


def parsear_ranks(contenido: str) -> Dict:
    """
    Parsea el contenido de un archivo Ranks.txt.
    
    Formato esperado:
    ```
    Asociación Uruguaya de Bridge   miércoles Pairs 11/2/2026
    Session 1 Section A
    5 Table 27 Board Howell Movement  
       Received 135 of 135 scores.
    =================================================================================================
    Rank Pair Names [OVERALL RANKS]                       Bds    Total   Max %Score      Hcp %WithHcp
    =================================================================================================
      1    1  Margarita Echenique & Rodrigo Fioritti       27   127,00   216  58,80 (1)  0,5    59,30
    ...
    ```
    
    Returns:
        Dict con keys: titulo, session, mesas, boards, movimiento, rankings
    """
    resultado = {
        'titulo': '',
        'session': '',
        'mesas': None,
        'boards': None,
        'movimiento': '',
        'rankings': []
    }
    
    lineas = contenido.strip().split('\n')
    
    # Primera línea: título con nombre y fecha
    if lineas:
        resultado['titulo'] = _limpiar_texto(lineas[0])
    
    # Buscar información de sesión, mesas, boards
    for linea in lineas[:10]:
        linea = _limpiar_texto(linea)
        
        # Session info
        if linea.lower().startswith('session'):
            resultado['session'] = linea
        
        # Mesas y boards: "5 Table 27 Board Howell Movement"
        match_info = re.search(r'(\d+)\s*Table[s]?\s+(\d+)\s*Board[s]?\s+(\w+)', linea, re.IGNORECASE)
        if match_info:
            resultado['mesas'] = int(match_info.group(1))
            resultado['boards'] = int(match_info.group(2))
            resultado['movimiento'] = match_info.group(3)
    
    # Parsear rankings
    # Formato: Rank Pair Names... Bds Total Max %Score Hcp %WithHcp
    # Ejemplo:   1    1  Margarita Echenique & Rodrigo Fioritti       27   127,00   216  58,80 (1)  0,5    59,30
    
    patron_ranking = re.compile(
        r'^\s*(\d+)\s+'           # Rank (posición)
        r'(\d+)\s+'               # Pair (número de pareja)
        r'(.+?)\s+'               # Nombres (captura todo hasta los números)
        r'(\d+)\s+'               # Boards
        r'([\d,\.]+)\s+'          # Total
        r'(\d+)\s+'               # Max
        r'([\d,\.]+)'             # %Score
        r'(?:\s*\(\d+\))?\s*'     # (rank opcional)
        r'([-\d,\.]+)\s+'         # Handicap
        r'([\d,\.]+)',            # %WithHcp
        re.IGNORECASE
    )
    
    for linea in lineas:
        linea_limpia = _limpiar_texto(linea)
        
        # Saltar líneas de separación y headers
        if '===' in linea or not linea_limpia:
            continue
        if 'Rank' in linea and 'Pair' in linea:
            continue
        if 'printed' in linea.lower():
            continue
            
        match = patron_ranking.match(linea_limpia)
        if match:
            nombre_completo = _limpiar_texto(match.group(3))
            nombre1, nombre2 = _parsear_nombres_pareja(nombre_completo)
            
            ranking = {
                'posicion': int(match.group(1)),
                'numero_pareja': int(match.group(2)),
                'nombre_jugador1': nombre1,
                'nombre_jugador2': nombre2,
                'boards_jugados': int(match.group(4)),
                'total_puntos': float(match.group(5).replace(',', '.')),
                'maximo_puntos': int(match.group(6)),
                'porcentaje': float(match.group(7).replace(',', '.')),
                'handicap': float(match.group(8).replace(',', '.')),
                'porcentaje_con_handicap': float(match.group(9).replace(',', '.'))
            }
            resultado['rankings'].append(ranking)
    
    return resultado


def parsear_travellers(contenido: str) -> Dict:
    """
    Parsea el contenido de un archivo Travellers.txt.
    
    Usa posiciones de columna extraídas de la línea de encabezado para
    evitar problemas con campos opcionales (Lead, NS+, NS-).
    
    Formato esperado:
    ```
    Asociación Uruguaya de Bridge   miércoles Pairs 11/2/2026
    Session 1 Section A
    Neuberg Top = 8
     =====================================================
     BOARD 1                                              
     NS  EW  Contract Dec Lead    NS+  NS-      MP      MP  NS                                    EW
     =====================================================
      5   8  5S-1      W           50            8       0  Carlos Zagarzazú & Jacqueline Pollak  Paula Zumarán & Jorge Rossolino       
    ...
    ```
    
    Returns:
        Dict con keys: titulo, session, neuberg_top, manos
    """
    resultado = {
        'titulo': '',
        'session': '',
        'neuberg_top': None,
        'manos': []
    }
    
    lineas = contenido.strip().split('\n')
    
    # Primera línea: título
    if lineas:
        resultado['titulo'] = _limpiar_texto(lineas[0])
    
    # Buscar información de sesión y Neuberg top
    for linea in lineas[:10]:
        linea_l = _limpiar_texto(linea)
        
        if linea_l.lower().startswith('session'):
            resultado['session'] = linea_l
        
        match_neuberg = re.search(r'Neuberg\s+Top\s*=\s*(\d+)', linea_l, re.IGNORECASE)
        if match_neuberg:
            resultado['neuberg_top'] = int(match_neuberg.group(1))
    
    # Parsear manos usando posiciones de columna
    board_actual = None
    patron_board = re.compile(r'BOARD\s+(\d+)', re.IGNORECASE)
    col_pos = None  # Posiciones de columna extraídas del encabezado
    
    for linea in lineas:
        linea_limpia = _limpiar_texto(linea)
        
        # Detectar nuevo board
        match_board = patron_board.search(linea_limpia)
        if match_board:
            board_actual = int(match_board.group(1))
            continue
        
        # Saltar líneas de separación y vacías
        if '===' in linea or not linea_limpia:
            continue
        if 'printed' in linea.lower():
            continue
        
        # Detectar línea de encabezado y extraer posiciones de columna
        if 'Contract' in linea and ('NS+' in linea or 'NS-' in linea):
            col_pos = _extraer_posiciones_traveller(linea)
            continue
        
        # Saltar headers que no pudimos usar para posiciones
        if 'Contract' in linea and 'Dec' in linea:
            continue
        
        # Intentar parsear como línea de datos
        if board_actual is not None and col_pos is not None:
            mano = _parsear_linea_mano_traveller(linea, col_pos, board_actual)
            if mano:
                resultado['manos'].append(mano)
    
    return resultado


def _extraer_posiciones_traveller(header: str) -> Dict:
    """
    Extrae las posiciones de inicio de cada columna a partir
    de la línea de encabezado del traveller.
    
    Header típico:
    ' NS  EW  Contract Dec Lead    NS+  NS-      MP      MP  NS ... EW'
    """
    pos = {}
    
    # Columnas con nombres únicos (fáciles de encontrar)
    for col_name in ('Contract', 'Dec', 'Lead', 'NS+', 'NS-'):
        idx = header.find(col_name)
        if idx >= 0:
            pos[col_name] = idx
    
    # Columnas MP: hay dos, después de NS-
    buscar_desde = pos.get('NS-', 0) + 3
    mp_indices = []
    s = buscar_desde
    while True:
        idx = header.find('MP', s)
        if idx < 0:
            break
        mp_indices.append(idx)
        s = idx + 2
    
    if len(mp_indices) >= 2:
        pos['MP_NS'] = mp_indices[0]
        pos['MP_EW'] = mp_indices[1]
    elif len(mp_indices) == 1:
        pos['MP_NS'] = mp_indices[0]
    
    # Columnas de nombres (NS y EW después de las columnas MP)
    if mp_indices:
        s = mp_indices[-1] + 2
        idx_ns = header.find('NS', s)
        if idx_ns >= 0:
            pos['Nombres_NS'] = idx_ns
        idx_ew = header.find('EW', s)
        if idx_ew >= 0:
            pos['Nombres_EW'] = idx_ew
    
    return pos


def _parsear_linea_mano_traveller(linea: str, pos: Dict, board_numero: int) -> Optional[Dict]:
    """
    Parsea una línea de datos del traveller usando posiciones de columna fijas.
    
    Extrae campos por posición en lugar de regex para evitar ambigüedad
    entre Lead (opcional), NS+ (opcional) y NS- (opcional).
    """
    # Parsear inicio con regex: número de pareja NS, EW, contrato, declarante
    match = re.match(r'\s*(\d+)\s+(\d+)\s+(\S+)\s+([NSEW])\*?', linea, re.IGNORECASE)
    if not match:
        return None
    
    pareja_ns = int(match.group(1))
    pareja_ew = int(match.group(2))
    contrato = match.group(3)
    declarante = match.group(4).upper()
    
    # Extender línea con espacios si es más corta que las posiciones esperadas
    max_pos = max(pos.values()) if pos else len(linea)
    padded = linea.ljust(max_pos + 50)
    
    # Extraer Lead (entre columna Lead y NS+)
    salida = None
    if 'Lead' in pos and 'NS+' in pos:
        salida_str = padded[pos['Lead']:pos['NS+']].strip()
        if salida_str:
            salida = salida_str
    
    # Extraer NS+ (entre columna NS+ y NS-)
    ns_positivo = None
    if 'NS+' in pos and 'NS-' in pos:
        val = padded[pos['NS+']:pos['NS-']].strip()
        if val:
            try:
                ns_positivo = int(val)
            except ValueError:
                pass
    
    # Extraer NS- (entre columna NS- y MP_NS)
    ns_negativo = None
    fin_ns_minus = pos.get('MP_NS', pos.get('NS-', 0) + 6)
    if 'NS-' in pos:
        val = padded[pos['NS-']:fin_ns_minus].strip()
        if val:
            try:
                ns_negativo = int(val)
            except ValueError:
                pass
    
    # Extraer MP NS (entre columna MP_NS y MP_EW)
    mp_ns = 0.0
    fin_mp_ns = pos.get('MP_EW', pos.get('MP_NS', 0) + 8)
    if 'MP_NS' in pos:
        val = padded[pos['MP_NS']:fin_mp_ns].strip()
        try:
            mp_ns = float(val.replace(',', '.'))
        except (ValueError, TypeError):
            pass
    
    # Extraer MP EW (entre columna MP_EW y Nombres_NS)
    mp_ew = 0.0
    fin_mp_ew = pos.get('Nombres_NS', pos.get('MP_EW', 0) + 8)
    if 'MP_EW' in pos:
        val = padded[pos['MP_EW']:fin_mp_ew].strip()
        try:
            mp_ew = float(val.replace(',', '.'))
        except (ValueError, TypeError):
            pass
    
    # Extraer nombres de parejas
    nombre_ns = ''
    nombre_ew = ''
    if 'Nombres_NS' in pos:
        if 'Nombres_EW' in pos:
            nombre_ns = _limpiar_texto(padded[pos['Nombres_NS']:pos['Nombres_EW']])
            nombre_ew = _limpiar_texto(padded[pos['Nombres_EW']:].rstrip())
        else:
            rest = _limpiar_texto(padded[pos['Nombres_NS']:].rstrip())
            partes = re.split(r'\s{2,}', rest)
            if len(partes) >= 2:
                nombre_ns = _limpiar_texto(partes[0])
                nombre_ew = _limpiar_texto(partes[1])
            else:
                nombre_ns = rest
    elif 'MP_EW' in pos:
        # Fallback: extraer nombres después de MP EW
        rest = padded[fin_mp_ew:].strip()
        if rest:
            partes = re.split(r'\s{2,}', rest)
            if len(partes) >= 2:
                nombre_ns = _limpiar_texto(partes[0])
                nombre_ew = _limpiar_texto(partes[1])
            else:
                nombre_ns = _limpiar_texto(rest)
    
    return {
        'board_numero': board_numero,
        'pareja_ns': pareja_ns,
        'pareja_ew': pareja_ew,
        'contrato': contrato,
        'declarante': declarante,
        'salida': salida,
        'puntos_ns_positivo': ns_positivo,
        'puntos_ns_negativo': ns_negativo,
        'mp_ns': mp_ns,
        'mp_ew': mp_ew,
        'nombre_pareja_ns': nombre_ns,
        'nombre_pareja_ew': nombre_ew,
    }


def emparejar_jugadores(nombre_completo: str, jugadores_db: list) -> Optional[int]:
    """
    Intenta encontrar un jugador en la base de datos que coincida con el nombre.
    
    Args:
        nombre_completo: Nombre completo del jugador (ej: "Margarita Echenique")
        jugadores_db: Lista de objetos Jugador de la base de datos
    
    Returns:
        ID del jugador si se encuentra, None si no
    """
    nombre_completo = _limpiar_texto(nombre_completo.lower())
    
    # Normalizar acentos para comparación más flexible
    import unicodedata
    def normalizar(texto):
        return ''.join(
            c for c in unicodedata.normalize('NFD', texto.lower())
            if unicodedata.category(c) != 'Mn'
        )
    
    nombre_normalizado = normalizar(nombre_completo)
    
    for jugador in jugadores_db:
        nombre_jugador = f"{jugador.nombre} {jugador.apellido}"
        if normalizar(nombre_jugador) == nombre_normalizado:
            return jugador.id
        
        # También probar apellido primero
        nombre_jugador_inv = f"{jugador.apellido} {jugador.nombre}"
        if normalizar(nombre_jugador_inv) == nombre_normalizado:
            return jugador.id
    
    return None


def calcular_puntos_ranking(posicion: int, porcentaje: float, tipo_torneo: str = 'handicap') -> float:
    """
    Calcula los puntos de ranking según el reglamento de la AUB.
    
    Para torneos de hándicap (Art. 38):
    - Top 4 por viento reciben puntos
    - >= 58%: puntos = % - 50 (redondeado hacia arriba)
    - 50% - 57.99%: puntos fijos según posición [10, 5, 3, 1]
    - < 50%: sin puntos
    
    Args:
        posicion: Posición final en el torneo (1-based)
        porcentaje: Porcentaje obtenido (con handicap)
        tipo_torneo: Tipo de torneo para determinar tabla de puntos
    
    Returns:
        Puntos de ranking a asignar
    """
    import math
    
    TABLAS_PUNTOS = {
        'handicap': [10, 5, 3, 1],
        'handicap_clubes_6': [3, 2, 1],
        'handicap_clubes_howell': [4, 2, 1],
        'handicap_final': [15, 10, 5, 3],
    }
    
    tabla = TABLAS_PUNTOS.get(tipo_torneo, TABLAS_PUNTOS['handicap'])
    
    if tipo_torneo.startswith('handicap'):
        # Lógica específica para torneos con hándicap
        if posicion <= len(tabla):
            if porcentaje >= 58:
                return math.ceil(porcentaje - 50)
            elif porcentaje >= 50:
                return tabla[posicion - 1]
        return 0
    else:
        # Otros torneos: tabla directa
        if 1 <= posicion <= len(tabla):
            return tabla[posicion - 1]
        return 0

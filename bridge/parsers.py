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
        linea = _limpiar_texto(linea)
        
        if linea.lower().startswith('session'):
            resultado['session'] = linea
        
        match_neuberg = re.search(r'Neuberg\s+Top\s*=\s*(\d+)', linea, re.IGNORECASE)
        if match_neuberg:
            resultado['neuberg_top'] = int(match_neuberg.group(1))
    
    # Parsear manos
    board_actual = None
    
    # Patrón para línea de BOARD
    patron_board = re.compile(r'BOARD\s+(\d+)', re.IGNORECASE)
    
    # Patrón para línea de resultado
    # Formato: NS EW Contract Dec Lead NS+ NS- MP MP NS_names EW_names
    # Ejemplo:  5   8  5S-1      W           50            8       0  Carlos Zagarzazú & Jacqueline Pollak  Paula Zumarán & Jorge Rossolino
    patron_resultado = re.compile(
        r'^\s*(\d+)\s+'           # NS pair number
        r'(\d+)\s+'               # EW pair number
        r'(\S+)\s+'               # Contract (e.g., 5S-1, 3NT=, 4Dx+1)
        r'([NSEW])\*?\s*'         # Declarer
        r'(\S*)\s*'               # Lead (puede estar vacío)
        r'(\d*)\s*'               # NS+ (puntos positivos para NS)
        r'(\d*)\s*'               # NS- (puntos negativos para NS)
        r'([\d,\.]+)\s+'          # MP NS
        r'([\d,\.]+)\s+'          # MP EW
        r'(.+)',                  # Nombres (resto de la línea)
        re.IGNORECASE
    )
    
    for linea in lineas:
        linea_limpia = _limpiar_texto(linea)
        
        # Detectar nuevo board
        match_board = patron_board.search(linea_limpia)
        if match_board:
            board_actual = int(match_board.group(1))
            continue
        
        # Saltar líneas de separación y headers
        if '===' in linea or not linea_limpia:
            continue
        if 'NS' in linea and 'EW' in linea and 'Contract' in linea:
            continue
            
        # Intentar parsear como resultado
        if board_actual is not None:
            match = patron_resultado.match(linea_limpia)
            if match:
                nombres = _limpiar_texto(match.group(10))
                
                # Separar nombres NS y EW (están concatenados, separados por espacios)
                # Buscar el patrón de dos parejas separadas por doble espacio o por el &
                # El formato es: "NS_nombre1 & NS_nombre2  EW_nombre1 & EW_nombre2"
                partes_nombres = re.split(r'\s{2,}', nombres)
                
                if len(partes_nombres) >= 2:
                    nombre_ns = _limpiar_texto(partes_nombres[0])
                    nombre_ew = _limpiar_texto(partes_nombres[1])
                else:
                    # Intentar separar por el segundo "&"
                    idx_segundo_amp = nombres.find('&', nombres.find('&') + 1)
                    if idx_segundo_amp > 0:
                        # Buscar el espacio antes del segundo nombre
                        parte1 = nombres[:idx_segundo_amp].strip()
                        parte2 = nombres[idx_segundo_amp:].strip()
                        # Encontrar dónde termina la primera pareja
                        ultimo_espacio = parte1.rfind('  ')
                        if ultimo_espacio > 0:
                            nombre_ns = parte1[:ultimo_espacio].strip()
                            nombre_ew = parte1[ultimo_espacio:].strip() + parte2
                        else:
                            nombre_ns = nombres
                            nombre_ew = ''
                    else:
                        nombre_ns = nombres
                        nombre_ew = ''
                
                ns_positivo = int(match.group(6)) if match.group(6) else None
                ns_negativo = int(match.group(7)) if match.group(7) else None
                
                mano = {
                    'board_numero': board_actual,
                    'pareja_ns': int(match.group(1)),
                    'pareja_ew': int(match.group(2)),
                    'contrato': match.group(3),
                    'declarante': match.group(4).upper(),
                    'salida': match.group(5) if match.group(5) else None,
                    'puntos_ns_positivo': ns_positivo,
                    'puntos_ns_negativo': ns_negativo,
                    'mp_ns': float(match.group(8).replace(',', '.')),
                    'mp_ew': float(match.group(9).replace(',', '.')),
                    'nombre_pareja_ns': nombre_ns,
                    'nombre_pareja_ew': nombre_ew
                }
                resultado['manos'].append(mano)
    
    return resultado


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

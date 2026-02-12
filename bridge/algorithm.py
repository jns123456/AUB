"""
Algoritmo de equilibrado de parejas para torneos de bridge.

Objetivo: dadas N parejas con sus handicaps promedio, asignar cada una
a Norte-Sur (NS) o Este-Oeste (EO) de forma que el promedio de handicaps
de ambos sentidos quede lo más parejo posible.

Esto es equivalente al problema de partición balanceada (balanced partition problem).
Para torneos pequeños (<=22 parejas) se usa búsqueda exhaustiva (óptimo garantizado).
Para torneos más grandes se usa un algoritmo greedy con mejora por búsqueda local.

Cada ejecución puede dar un resultado DIFERENTE (aleatorio) entre las soluciones
igualmente óptimas, lo que permite re-equilibrar y obtener asignaciones distintas.
"""

import random
from itertools import combinations


def equilibrar_parejas(parejas):
    """
    Función principal de equilibrado.

    Args:
        parejas: lista de dicts con al menos 'id' y 'handicap_pareja' (promedio de ambos jugadores).

    Returns:
        dict con:
            - 'ns': lista de parejas asignadas a Norte-Sur
            - 'eo': lista de parejas asignadas a Este-Oeste
            - 'ns_promedio': promedio de handicap NS
            - 'eo_promedio': promedio de handicap EO
            - 'diferencia': diferencia absoluta entre promedios
    """
    n = len(parejas)

    if n == 0:
        return {'ns': [], 'eo': [], 'ns_promedio': 0, 'eo_promedio': 0, 'diferencia': 0}

    if n == 1:
        return {
            'ns': [parejas[0]],
            'eo': [],
            'ns_promedio': parejas[0]['handicap_pareja'],
            'eo_promedio': 0,
            'diferencia': parejas[0]['handicap_pareja'],
        }

    # Elegir algoritmo según tamaño
    if n <= 22:
        ns, eo = _equilibrar_optimo(parejas)
    else:
        ns, eo = _equilibrar_greedy_mejorado(parejas)

    ns_promedio = sum(p['handicap_pareja'] for p in ns) / len(ns) if ns else 0
    eo_promedio = sum(p['handicap_pareja'] for p in eo) / len(eo) if eo else 0

    return {
        'ns': ns,
        'eo': eo,
        'ns_promedio': round(ns_promedio, 2),
        'eo_promedio': round(eo_promedio, 2),
        'diferencia': round(abs(ns_promedio - eo_promedio), 2),
    }


def _equilibrar_optimo(parejas):
    """
    Búsqueda exhaustiva para encontrar TODAS las particiones óptimas,
    y elegir una al azar.
    Garantiza el mejor equilibrio posible, con variedad al re-ejecutar.
    Viable para n <= 22 parejas (C(22,11) = 705,432 combinaciones).
    """
    n = len(parejas)
    ns_size = n // 2
    eo_size = n - ns_size

    handicaps = [p['handicap_pareja'] for p in parejas]
    total_sum = sum(handicaps)

    EPSILON = 1e-9  # Tolerancia para comparación de floats
    MAX_SOLUCIONES = 500

    best_diff = float('inf')
    mejores_soluciones = []
    total_encontradas = 0  # Para reservoir sampling

    for ns_indices in combinations(range(n), ns_size):
        ns_sum = sum(handicaps[i] for i in ns_indices)
        eo_sum = total_sum - ns_sum

        ns_avg = ns_sum / ns_size if ns_size > 0 else 0
        eo_avg = eo_sum / eo_size if eo_size > 0 else 0

        diff = abs(ns_avg - eo_avg)

        if diff < best_diff - EPSILON:
            # Nueva mejor diferencia: resetear lista
            best_diff = diff
            mejores_soluciones = [set(ns_indices)]
            total_encontradas = 1
        elif abs(diff - best_diff) <= EPSILON:
            # Misma diferencia óptima (con tolerancia float)
            total_encontradas += 1
            if len(mejores_soluciones) < MAX_SOLUCIONES:
                mejores_soluciones.append(set(ns_indices))
            else:
                # Reservoir sampling para distribución uniforme
                idx = random.randint(0, total_encontradas - 1)
                if idx < MAX_SOLUCIONES:
                    mejores_soluciones[idx] = set(ns_indices)

    # Elegir una solución al azar entre las óptimas
    elegida = random.choice(mejores_soluciones)

    ns = [parejas[i] for i in range(n) if i in elegida]
    eo = [parejas[i] for i in range(n) if i not in elegida]

    # Mezclar el orden dentro de cada grupo
    random.shuffle(ns)
    random.shuffle(eo)

    return ns, eo


def _equilibrar_greedy_mejorado(parejas):
    """
    Algoritmo greedy con mejora por búsqueda local (intercambios).
    Para torneos con más de 22 parejas.

    Incluye aleatorización para producir resultados diferentes en cada ejecución:
    1. Mezclar las parejas aleatoriamente.
    2. Asignar greedily al grupo con menor suma (manteniendo tamaños balanceados).
    3. Mejorar con intercambios locales (swap de una pareja NS con una EO).
    """
    n = len(parejas)
    ns_target = n // 2
    eo_target = n - ns_target

    # Paso 1: Mezclar aleatoriamente antes del greedy
    shuffled_pairs = list(parejas)
    random.shuffle(shuffled_pairs)

    ns = []
    eo = []
    ns_sum = 0
    eo_sum = 0

    for pair in shuffled_pairs:
        if len(ns) >= ns_target:
            eo.append(pair)
            eo_sum += pair['handicap_pareja']
        elif len(eo) >= eo_target:
            ns.append(pair)
            ns_sum += pair['handicap_pareja']
        else:
            if ns_sum <= eo_sum:
                ns.append(pair)
                ns_sum += pair['handicap_pareja']
            else:
                eo.append(pair)
                eo_sum += pair['handicap_pareja']

    # Paso 2: Mejora por intercambios locales
    improved = True
    while improved:
        improved = False
        ns_avg = ns_sum / len(ns) if ns else 0
        eo_avg = eo_sum / len(eo) if eo else 0
        current_diff = abs(ns_avg - eo_avg)

        best_swap = None
        best_new_diff = current_diff

        for i, ns_pair in enumerate(ns):
            for j, eo_pair in enumerate(eo):
                new_ns_sum = ns_sum - ns_pair['handicap_pareja'] + eo_pair['handicap_pareja']
                new_eo_sum = eo_sum - eo_pair['handicap_pareja'] + ns_pair['handicap_pareja']
                new_ns_avg = new_ns_sum / len(ns)
                new_eo_avg = new_eo_sum / len(eo)
                new_diff = abs(new_ns_avg - new_eo_avg)

                if new_diff < best_new_diff:
                    best_new_diff = new_diff
                    best_swap = (i, j)

        if best_swap and best_new_diff < current_diff:
            i, j = best_swap
            ns_sum = ns_sum - ns[i]['handicap_pareja'] + eo[j]['handicap_pareja']
            eo_sum = eo_sum - eo[j]['handicap_pareja'] + ns[i]['handicap_pareja']
            ns[i], eo[j] = eo[j], ns[i]
            improved = True

    return ns, eo

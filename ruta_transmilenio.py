#!/usr/bin/env python3
"""
Sistema inteligente de rutas para un sistema de transporte masivo (modelo
simplificado de TransMilenio, Bogotá).

Arquitectura (Benítez, 2014):
  - Cap. 2  Lógica y representación del conocimiento: hechos y reglas (Horn).
  - Cap. 3  Sistemas basados en reglas: motor de encadenamiento hacia adelante.
  - Cap. 9  Búsqueda heurística: algoritmo A* con heurística admisible.

Nota: coordenadas y velocidades son APROXIMADAS y con fines didácticos.

Uso:
    python ruta_transmilenio.py                    # demo con varios casos
    python ruta_transmilenio.py Portal_Americas Calle_100
    python ruta_transmilenio.py --reglas           # muestra reglas y hechos derivados
"""
import heapq
import math
import sys
from collections import defaultdict

# ---------------------------------------------------------------------------
# 1. BASE DE CONOCIMIENTO: hechos
#    estacion(E, lat, lon)      linea(L, [estaciones en orden])
# ---------------------------------------------------------------------------
ESTACIONES = {
    "Calle_100":       (4.6845, -74.0575),
    "Calle_72":        (4.6590, -74.0640),
    "Marly":           (4.6270, -74.0665),
    "Calle_26":        (4.6135, -74.0685),
    "Jimenez":         (4.6020, -74.0745),
    "Hospitales":      (4.5930, -74.0810),
    "Restrepo":        (4.5840, -74.0960),
    "Portal_Eldorado": (4.6510, -74.1440),
    "Modelia":         (4.6600, -74.1180),
    "CAN":             (4.6350, -74.0950),
    "Portal_Americas": (4.6210, -74.1890),
    "Marsella":        (4.6330, -74.1300),
    "Puente_Aranda":   (4.6150, -74.1120),
    "Ricaurte":        (4.6110, -74.0960),
    "Paloquemao":      (4.6220, -74.0900),
    "Movistar_Arena":  (4.6520, -74.0770),
    "Calle_72_NQS":    (4.6600, -74.0740),
}

LINEAS = {
    "Caracas":  ["Calle_100", "Calle_72", "Marly", "Calle_26", "Jimenez",
                 "Hospitales", "Restrepo"],
    "Calle26":  ["Portal_Eldorado", "Modelia", "CAN", "Calle_26"],
    "Americas": ["Portal_Americas", "Marsella", "Puente_Aranda", "Ricaurte",
                 "Jimenez"],
    "NQS":      ["Ricaurte", "Paloquemao", "CAN", "Movistar_Arena",
                 "Calle_72_NQS"],
}

# Parámetros del modelo de costo (minutos)
V_MAX_KMH = 22.0      # velocidad comercial máxima aprox.
PARADA_MIN = 1.0      # tiempo de parada por estación
TRANSBORDO_MIN = 4.0  # penalización por cambiar de troncal


def haversine_km(a, b):
    """Distancia en km entre dos estaciones (lat, lon)."""
    (la1, lo1), (la2, lo2) = ESTACIONES[a], ESTACIONES[b]
    p1, p2 = math.radians(la1), math.radians(la2)
    dphi, dl = p2 - p1, math.radians(lo2 - lo1)
    h = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(h))


# ---------------------------------------------------------------------------
# 2. MOTOR DE REGLAS (encadenamiento hacia adelante)
#    Hechos = tuplas ("predicado", arg1, arg2, ...)
#    Reglas = funciones que, dada la memoria de trabajo, devuelven hechos nuevos
# ---------------------------------------------------------------------------
REGLAS_TEXTO = [
    "R1: conecta(E1,E2,L) <- siguiente(E1,E2,L)",
    "R2: conecta(E2,E1,L) <- siguiente(E1,E2,L)              [líneas bidireccionales]",
    "R3: transbordo(E,L1,L2) <- en_linea(E,L1) ^ en_linea(E,L2) ^ L1 != L2",
    "R4: costo(E1,E2,L,C) <- conecta(E1,E2,L) ^ C = dist(E1,E2)/vmax*60 + parada",
]


def cargar_hechos():
    hechos = set()
    for e in ESTACIONES:
        hechos.add(("estacion", e))
    for linea, seq in LINEAS.items():
        for e in seq:
            hechos.add(("en_linea", e, linea))
        for e1, e2 in zip(seq, seq[1:]):
            hechos.add(("siguiente", e1, e2, linea))
    return hechos


def r1(h):
    return {("conecta", a, b, l) for (p, a, b, l) in _f(h, "siguiente")}


def r2(h):
    return {("conecta", b, a, l) for (p, a, b, l) in _f(h, "siguiente")}


def r3(h):
    por_estacion = defaultdict(set)
    for (_, e, l) in _f(h, "en_linea"):
        por_estacion[e].add(l)
    return {("transbordo", e, l1, l2)
            for e, ls in por_estacion.items() for l1 in ls for l2 in ls if l1 != l2}


def r4(h):
    nuevos = set()
    for (_, a, b, l) in _f(h, "conecta"):
        c = haversine_km(a, b) / V_MAX_KMH * 60 + PARADA_MIN
        nuevos.add(("costo", a, b, l, round(c, 3)))
    return nuevos


def _f(hechos, predicado):
    return [f for f in hechos if f[0] == predicado]


REGLAS = [r1, r2, r3, r4]


def encadenamiento_adelante(hechos):
    """Aplica las reglas hasta alcanzar el punto fijo (no se derivan hechos nuevos)."""
    memoria = set(hechos)
    iteraciones = 0
    while True:
        iteraciones += 1
        nuevos = set()
        for regla in REGLAS:
            nuevos |= regla(memoria) - memoria
        if not nuevos:
            return memoria, iteraciones
        memoria |= nuevos


# ---------------------------------------------------------------------------
# 3. BÚSQUEDA HEURÍSTICA A*
#    Estado = (estación, línea actual). f(n) = g(n) + h(n)
#    h(n) = distancia en línea recta / velocidad máxima  (admisible: nunca
#    sobrestima, porque ignora paradas y transbordos).
# ---------------------------------------------------------------------------
def heuristica(estacion, meta):
    return haversine_km(estacion, meta) / V_MAX_KMH * 60


def a_estrella(memoria, origen, destino):
    vecinos = defaultdict(list)          # (estación, línea) -> [(estación2, línea, costo, acción)]
    for (_, a, b, l, c) in _f(memoria, "costo"):
        vecinos[(a, l)].append(((b, l), c, f"viajar {a} -> {b} [{l}]"))
    for (_, e, l1, l2) in _f(memoria, "transbordo"):
        vecinos[(e, l1)].append(((e, l2), TRANSBORDO_MIN, f"transbordar en {e}: {l1} -> {l2}"))

    lineas_origen = [l for (_, e, l) in _f(memoria, "en_linea") if e == origen]
    frontera, contador, expandidos = [], 0, 0
    g = {}
    padre = {}
    for l in lineas_origen:
        s = (origen, l)
        g[s] = 0.0
        padre[s] = None
        heapq.heappush(frontera, (heuristica(origen, destino), contador, s))
        contador += 1

    while frontera:
        f, _, actual = heapq.heappop(frontera)
        if f > g[actual] + heuristica(actual[0], destino) + 1e-9:
            continue  # entrada obsoleta
        expandidos += 1
        if actual[0] == destino:
            pasos = []
            s = actual
            while padre[s] is not None:
                s, accion = padre[s]
                pasos.append(accion)
            return g[actual], pasos[::-1], expandidos
        for (sig, costo, accion) in vecinos[actual]:
            nuevo_g = g[actual] + costo
            if nuevo_g < g.get(sig, float("inf")):
                g[sig] = nuevo_g
                padre[sig] = (actual, accion)
                heapq.heappush(frontera, (nuevo_g + heuristica(sig[0], destino), contador, sig))
                contador += 1
    return None, [], expandidos


# ---------------------------------------------------------------------------
# 4. Interfaz
# ---------------------------------------------------------------------------
def resumir(pasos):
    """Agrupa tramos consecutivos de la misma línea para leer mejor la ruta."""
    salida, tramo = [], None
    for p in pasos:
        if p.startswith("viajar"):
            _, resto = p.split(" ", 1)
            ruta, linea = resto.rsplit(" [", 1)
            a, b = ruta.split(" -> ")
            linea = linea.rstrip("]")
            if tramo and tramo["linea"] == linea:
                tramo["fin"] = b
                tramo["n"] += 1
            else:
                if tramo:
                    salida.append(tramo)
                tramo = {"linea": linea, "ini": a, "fin": b, "n": 1}
        else:
            if tramo:
                salida.append(tramo)
                tramo = None
            salida.append(p)
    if tramo:
        salida.append(tramo)
    return salida


def imprimir_ruta(memoria, origen, destino):
    for e in (origen, destino):
        if e not in ESTACIONES:
            print(f"Estación desconocida: {e}")
            print("Estaciones válidas:", ", ".join(sorted(ESTACIONES)))
            return
    costo, pasos, expandidos = a_estrella(memoria, origen, destino)
    print(f"\n=== Ruta {origen} -> {destino} ===")
    if costo is None:
        print("No existe ruta.")
        return
    for i, t in enumerate(resumir(pasos), 1):
        if isinstance(t, dict):
            print(f" {i}. Tomar troncal {t['linea']}: {t['ini']} -> {t['fin']} ({t['n']} tramos)")
        else:
            print(f" {i}. {t}")
    print(f" Tiempo estimado: {costo:.1f} min | nodos expandidos por A*: {expandidos}")


def main():
    hechos = cargar_hechos()
    memoria, it = encadenamiento_adelante(hechos)

    if "--reglas" in sys.argv:
        print("REGLAS DE LA BASE DE CONOCIMIENTO")
        for r in REGLAS_TEXTO:
            print("  ", r)
        print(f"\nHechos iniciales: {len(hechos)} | Hechos tras inferencia: {len(memoria)} "
              f"| Iteraciones hasta punto fijo: {it}")
        for pred in ("conecta", "transbordo", "costo"):
            print(f"  {pred}: {len(_f(memoria, pred))} hechos derivados")
        print("  Transbordos:", sorted({f[1] for f in _f(memoria, 'transbordo')}))
        return

    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) == 2:
        imprimir_ruta(memoria, args[0], args[1])
    else:
        for o, d in [("Portal_Americas", "Calle_100"),
                     ("Portal_Eldorado", "Restrepo"),
                     ("Calle_100", "Calle_72_NQS"),
                     ("Marsella", "Hospitales")]:
            imprimir_ruta(memoria, o, d)


if __name__ == "__main__":
    main()

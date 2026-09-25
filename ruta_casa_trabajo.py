#!/usr/bin/env python3
"""
Ruta casa -> trabajo: Portal 20 de Julio -> Estación Prado (Autopista Norte, Cl 128).

Base de conocimiento en reglas lógicas + búsqueda heurística A*
(Benítez, 2014: cap. 2 lógica, cap. 3 sistemas de reglas, cap. 9 búsqueda heurística).

Tiempos: medidos por el usuario (incluyen esperas y abordaje). Coordenadas aproximadas,
usadas solo para la heurística.

Uso:
    python3 ruta_casa_trabajo.py                    # escenario normal y pesimista
    python3 ruta_casa_trabajo.py --reglas           # muestra las reglas
    python3 ruta_casa_trabajo.py --novedad C25=45   # simula un retraso de 45 min en C25
"""
import heapq
import math
import sys
from collections import defaultdict

# ---------------------------------------------------------------------------
# 1. HECHOS (conocimiento del dominio)
# ---------------------------------------------------------------------------
ORIGEN, DESTINO = "Portal_20_Julio", "Prado"

# estacion(E, lat, lon): coordenadas aproximadas (solo para la heurística)
ESTACIONES = {
    "Portal_20_Julio": (4.5700, -74.0960),
    "Jimenez":         (4.6020, -74.0745),
    "Virrey":          (4.6700, -74.0570),
    "Calle_30":        (4.6240, -74.0870),
    "Calle_75":        (4.6640, -74.0730),
    "Prado":           (4.7040, -74.0545),
}

# tramo(origen, destino, servicio, tipo_via, minutos_medidos)
# Si minutos_medidos es None, una regla lo calcula con distancia y velocidad de la vía.
TRAMOS = [
    # L18: directo por la Caracas (semáforos, obras del metro, congestión)
    ("Portal_20_Julio", "Jimenez", "L18", "congestionada", 30),
    ("Jimenez",         "Virrey",  "L18", "obras",         30),   # entrada/salida de camiones
    ("Virrey",          "Prado",   "L18", "congestionada", 30),
    # C25 + B12: tiempos estables (el usuario siempre logra abordar)
    ("Portal_20_Julio", "Calle_30", "C25", "lenta",  15),        # bajando por la Calle 6 hasta la 30
    ("Calle_30",        "Calle_75", "C25", "rapida", 15),        # por la 30 hacia el norte
    ("Calle_75",        "Prado",    "B12", "media",  30),
]

# inestable(origen, destino, servicio, minutos_extra_en_el_peor_caso)
INESTABLES = [("Jimenez", "Virrey", "L18", 30)]   # con obras, L18 puede llegar a ~2 h

# velocidad(tipo_via, km/h): solo para tramos sin tiempo medido (regla R1b)
VELOCIDADES = {"congestionada": 9.2, "obras": 9.2, "lenta": 14.0, "media": 25.0, "rapida": 45.0}
FACTOR_RUTA = 1.3          # la ruta real es ~30% más larga que la línea recta

# lleno(S): el servicio va repleto (el usuario siempre logra subirse)
LLENOS = {"L18", "C25", "B12"}

# Parámetros (minutos). Los tiempos medidos ya incluyen espera y abordaje.
ABORDAJE_BASE = 0.0
PENALIZ_LLENO = 0.0        # súbelo a 2.0 para castigar buses repletos (what-if)
ESPERA_TRANSBORDO = 0.0
V_MAX_KMH = max(VELOCIDADES.values())   # cota de velocidad para la heurística

NOVEDADES = {}             # novedad(S, min): retraso extra; se llena con --novedad


def haversine_km(a, b):
    (la1, lo1), (la2, lo2) = ESTACIONES[a], ESTACIONES[b]
    p1, p2 = math.radians(la1), math.radians(la2)
    dphi, dl = p2 - p1, math.radians(lo2 - lo1)
    h = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(h))


# ---------------------------------------------------------------------------
# 2. REGLAS (motor de encadenamiento hacia adelante)
# ---------------------------------------------------------------------------
REGLAS_TEXTO = [
    "R1a: conecta(E1,E2,S,M)     <- tramo(E1,E2,S,Via,M) ^ M medido",
    "R1b: conecta(E1,E2,S,M)     <- tramo(E1,E2,S,Via,nulo) ^ velocidad(Via,V) ^ M = dist*1.3/V*60",
    "R1c: conecta(E1,E2,S,M+X)   <- (R1a v R1b) ^ inestable(E1,E2,S,X) ^ escenario(pesimista)",
    "R2:  en_servicio(E,S)       <- tramo(E,_,S,_,_)  v  tramo(_,E,S,_,_)",
    "R3:  abordaje(S,M)          <- servicio(S) ^ M = base + (penal. si lleno(S)) + novedad(S)",
    "R4:  transbordo(E,S1,S2,M)  <- en_servicio(E,S1) ^ en_servicio(E,S2) ^ S1 != S2",
    "                              ^ abordaje(S2,A) ^ M = espera + A",
]


def hechos_iniciales(pesimista=False):
    h = set()
    for e in ESTACIONES:
        h.add(("estacion", e))
    for (a, b, s, via, med) in TRAMOS:
        h.add(("tramo", a, b, s, via, med))
        h.add(("servicio", s))
    for via, v in VELOCIDADES.items():
        h.add(("velocidad", via, v))
    for (a, b, s, extra) in INESTABLES:
        h.add(("inestable", a, b, s, extra))
    for s in LLENOS:
        h.add(("lleno", s))
    for s, m in NOVEDADES.items():
        h.add(("novedad", s, m))
    if pesimista:
        h.add(("escenario", "pesimista"))
    return h


def _f(hechos, pred):
    return [f for f in hechos if f[0] == pred]


def r1(h):
    vel = {f[1]: f[2] for f in _f(h, "velocidad")}
    extras = {(f[1], f[2], f[3]): f[4] for f in _f(h, "inestable")}
    pesimista = ("escenario", "pesimista") in h
    out = set()
    for (_, a, b, s, via, med) in _f(h, "tramo"):
        if med is not None:                                              # R1a
            m = float(med)
        elif via in vel:                                                 # R1b
            m = round(haversine_km(a, b) * FACTOR_RUTA / vel[via] * 60, 1)
        else:
            continue
        if pesimista:                                                    # R1c
            m += extras.get((a, b, s), 0)
        out.add(("conecta", a, b, s, m, via))
    return out


def r2(h):
    out = set()
    for (_, a, b, s, via, med) in _f(h, "tramo"):
        out.add(("en_servicio", a, s))
        out.add(("en_servicio", b, s))
    return out


def r3(h):
    llenos = {f[1] for f in _f(h, "lleno")}
    nov = {f[1]: f[2] for f in _f(h, "novedad")}
    out = set()
    for (_, s) in _f(h, "servicio"):
        m = ABORDAJE_BASE + (PENALIZ_LLENO if s in llenos else 0) + nov.get(s, 0)
        out.add(("abordaje", s, m))
    return out


def r4(h):
    ab = {f[1]: f[2] for f in _f(h, "abordaje")}
    por_est = defaultdict(set)
    for (_, e, s) in _f(h, "en_servicio"):
        por_est[e].add(s)
    out = set()
    for e, ss in por_est.items():
        for s1 in ss:
            for s2 in ss:
                if s1 != s2 and s2 in ab:
                    out.add(("transbordo", e, s1, s2, ESPERA_TRANSBORDO + ab[s2]))
    return out


REGLAS = [r1, r2, r3, r4]


def encadenamiento_adelante(hechos):
    memoria, it = set(hechos), 0
    while True:
        it += 1
        nuevos = set()
        for r in REGLAS:
            nuevos |= r(memoria) - memoria
        if not nuevos:
            return memoria, it
        memoria |= nuevos


# ---------------------------------------------------------------------------
# 3. BÚSQUEDA A*   Estado = (estación, servicio en el que voy)
# ---------------------------------------------------------------------------
def h_heur(est, meta):
    return haversine_km(est, meta) / V_MAX_KMH * 60


def verificar_admisibilidad(mem):
    """La heurística es admisible si nunca supera el tiempo real de un tramo."""
    for (_, a, b, s, m, via) in _f(mem, "conecta"):
        if h_heur(a, b) > m + 1e-9:
            print(f"AVISO: tramo {a}->{b} [{s}] implica velocidad > {V_MAX_KMH} km/h; "
                  "sube V_MAX_KMH o revisa el tiempo.")


def construir_vecinos(mem, origen=None):
    vec = defaultdict(list)
    for (_, a, b, s, m, via) in _f(mem, "conecta"):
        vec[(a, s)].append(((b, s), m, f"viajar {a} -> {b} en {s}, vía {via} ({m:.0f} min)"))
    for (_, e, s1, s2, m) in _f(mem, "transbordo"):
        if e == origen:      # en el origen se elige el servicio al abordar; no se transborda
            continue
        vec[(e, s1)].append(((e, s2), m, f"transbordar en {e}: {s1} -> {s2} ({m:.0f} min)"))
    return vec


def inicios(mem, origen):
    ab = {f[1]: f[2] for f in _f(mem, "abordaje")}
    return [((origen, s), ab[s], f"abordar {s} en {origen} ({ab[s]:.0f} min)")
            for (_, e, s) in _f(mem, "en_servicio") if e == origen and s in ab]


def a_estrella(mem, origen, destino):
    vec = construir_vecinos(mem, origen)
    g, padre, frontera, cont, expandidos = {}, {}, [], 0, 0
    for (est, costo, acc) in inicios(mem, origen):
        g[est], padre[est] = costo, (None, acc)
        heapq.heappush(frontera, (costo + h_heur(origen, destino), cont, est))
        cont += 1
    while frontera:
        f, _, cur = heapq.heappop(frontera)
        if f > g[cur] + h_heur(cur[0], destino) + 1e-9:
            continue
        expandidos += 1
        if cur[0] == destino:
            pasos, s = [], cur
            while s is not None:
                s, acc = padre[s]
                pasos.append(acc)
            return g[cur], pasos[::-1], expandidos
        for (sig, c, acc) in vec[cur]:
            ng = g[cur] + c
            if ng < g.get(sig, float("inf")):
                g[sig], padre[sig] = ng, (cur, acc)
                heapq.heappush(frontera, (ng + h_heur(sig[0], destino), cont, sig))
                cont += 1
    return None, [], expandidos


def todas_las_rutas(mem, origen, destino):
    """Enumera todas las rutas posibles (grafo pequeño) para compararlas con A*."""
    vec = construir_vecinos(mem, origen)
    res = []

    def dfs(est, g, pasos, vistos):
        if est[0] == destino:
            res.append((g, pasos))
            return
        for (sig, c, acc) in vec[est]:
            if sig not in vistos:
                dfs(sig, g + c, pasos + [acc], vistos | {sig})

    for (est, c, acc) in inicios(mem, origen):
        dfs(est, c, [acc], {est})
    return sorted(res, key=lambda r: r[0])


def nombre_ruta(pasos):
    orden = ["L18", "C25", "B12"]
    serv = {p.split(" en ")[1].split(",")[0] for p in pasos if p.startswith("viajar")}
    return " + ".join(sorted(serv, key=orden.index))


# ---------------------------------------------------------------------------
# 4. Ejecución
# ---------------------------------------------------------------------------
def main():
    if "--novedad" in sys.argv:                     # ejemplo: --novedad C25=45
        serv, minutos = sys.argv[sys.argv.index("--novedad") + 1].split("=")
        NOVEDADES[serv] = float(minutos)

    if "--reglas" in sys.argv:
        mem, it = encadenamiento_adelante(hechos_iniciales())
        print("REGLAS:")
        for r in REGLAS_TEXTO:
            print("  ", r)
        print(f"\nHechos iniciales: {len(hechos_iniciales())} | tras inferencia: {len(mem)} "
              f"| iteraciones: {it}")
        for p in ("conecta", "en_servicio", "abordaje", "transbordo"):
            print(f"  {p}: {len(_f(mem, p))}")
        return

    if NOVEDADES:
        print("Novedades activas:", NOVEDADES)

    for pesimista in (False, True):
        mem, _ = encadenamiento_adelante(hechos_iniciales(pesimista))
        verificar_admisibilidad(mem)
        etiqueta = "PESIMISTA (obras, camiones en Jiménez)" if pesimista else "NORMAL"
        print(f"\n########## Escenario {etiqueta} ##########")
        costo, pasos, exp = a_estrella(mem, ORIGEN, DESTINO)
        print(f"Mejor ruta según A*: {ORIGEN} -> {DESTINO}")
        for i, p in enumerate(pasos, 1):
            print(f" {i}. {p}")
        print(f" TOTAL: {costo:.0f} min | nodos expandidos: {exp}")
        print("Comparación de todas las rutas posibles:")
        for i, (c, pasos) in enumerate(todas_las_rutas(mem, ORIGEN, DESTINO), 1):
            print(f" Ruta {i}: {nombre_ruta(pasos):<10} {c:.0f} min")


if __name__ == "__main__":
    main()

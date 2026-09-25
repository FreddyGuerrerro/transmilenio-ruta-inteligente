Sistema inteligente de rutas en transporte masivo
Sistema que, a partir de una base de conocimiento escrita en reglas lógicas, calcula la mejor ruta entre dos puntos del sistema de transporte masivo, usando el algoritmo de búsqueda heurística A*.

Basado en los conceptos de:

Benítez, R. (2014). Inteligencia artificial avanzada. Barcelona: Editorial UOC. Cap. 2 (Lógica y representación del conocimiento), Cap. 3 (Sistemas basados en reglas) y Cap. 9 (Técnicas basadas en búsquedas heurísticas).

Archivos
ruta_transmilenio.py: modelo genérico con 17 estaciones y 4 troncales (Caracas, Calle 26, Américas, NQS), para cualquier par de estaciones.
ruta_casa_trabajo.py: caso real, mi recorrido diario entre el Portal 20 de Julio y la estación Prado (Autopista Norte, Cl. 128), comparando dos rutas alternativas (L18 vs. C25 + B12).
Arquitectura
Capítulo	Concepto	Dónde está en el código
Cap. 2	Hechos y reglas lógicas	tramo, en_servicio, lleno, etc.
Cap. 3	Motor de reglas (encadenamiento hacia adelante)	encadenamiento_adelante()
Cap. 9	Búsqueda heurística A*	a_estrella()
El sistema primero carga hechos (estaciones, tramos, tiempos conocidos). Luego un motor de reglas deduce nueva información (conexiones, transbordos, tiempos de viaje) mediante encadenamiento hacia adelante, hasta llegar a un punto fijo. Finalmente, A* busca sobre esos hechos derivados la ruta de menor tiempo, usando como heurística la distancia en línea recta dividida por la velocidad máxima posible (heurística admisible: nunca sobreestima).

Cómo ejecutar
python3 ruta_transmilenio.py                     # ejemplos genéricos
python3 ruta_transmilenio.py Portal_Americas Calle_100
python3 ruta_transmilenio.py --reglas            # muestra las reglas y hechos inferidos

python3 ruta_casa_trabajo.py                     # mi caso: escenario normal y pesimista
python3 ruta_casa_trabajo.py --reglas
python3 ruta_casa_trabajo.py --novedad C25=45    # simula un retraso de 45 min en la C25
Resultados: caso real (Portal 20 de Julio → Prado)
Ruta	Escenario normal	Escenario pesimista (obras del metro)
C25 + B12 (transbordo en Calle 75)	60 min	60 min
L18 (directa por la Caracas)	90 min	120 min
El sistema elige siempre C25 + B12, lo que coincide con mi experiencia real: esta ruta es más larga en distancia pero mucho más estable, porque L18 pasa por un tramo (Jiménez–Virrey) afectado por las obras del metro, con tiempos muy variables.

Al simular un retraso de 45 min en la C25 (--novedad C25=45), el sistema muestra que, en el escenario normal, L18 pasaría a ser más rápida (90 min frente a 105 min), lo que confirma que el sistema recalcula la mejor decisión según cambien los hechos, tal como lo haría un sistema experto.

Limitaciones
Los tiempos del caso real fueron reportados por el usuario e incluyen espera y abordaje; los del modelo genérico son estimaciones.
Las coordenadas de las estaciones son aproximadas y solo se usan para la heurística de A*, no para calcular distancias reales.
El modelo genérico (ruta_transmilenio.py) no representa la topología real de TransMilenio; es una simplificación con fines didácticos.

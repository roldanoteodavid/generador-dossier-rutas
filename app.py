import streamlit as st
import gpxpy
import matplotlib.pyplot as plt
import datetime
import io

# --- 1. BASE DE DATOS DE LA TABLA ---
DATOS_RAMAS = {
    "Colonia": {"muy baja": [2.4, 200, 360], "baja": [2.7, 225, 405], "media": [3.0, 250, 450], "alta": [3.15, 263, 473], "muy alta": [3.3, 275, 495]},
    "Manada": {"muy baja": [2.6, 240, 400], "baja": [2.93, 270, 450], "media": [3.25, 300, 500], "alta": [3.41, 315, 525], "muy alta": [3.58, 330, 550]},
    "Tropa": {"muy baja": [2.8, 280, 440], "baja": [3.15, 315, 495], "media": [3.5, 350, 550], "alta": [3.68, 368, 578], "muy alta": [3.85, 385, 605]},
    "Escultas": {"muy baja": [3.2, 320, 480], "baja": [3.6, 360, 540], "media": [4.0, 400, 600], "alta": [4.2, 420, 630], "muy alta": [4.4, 440, 660]},
    "Clan": {"muy baja": [3.2, 320, 480], "baja": [3.6, 360, 540], "media": [4.0, 400, 600], "alta": [4.2, 420, 630], "muy alta": [4.4, 440, 660]}
}

# --- 2. FUNCIONES ORIGINALES (SEGMENTACIÓN FIABLE) ---
def calculate_time(tramo_dist_km, tramo_desnivel_m, tramo_type, v_plano, v_subida, v_bajada):
    tiempo_llano = tramo_dist_km / v_plano if v_plano > 0 else 0
    if tramo_type == 'subida': tiempo_desnivel = tramo_desnivel_m / v_subida
    elif tramo_type == 'bajada': tiempo_desnivel = abs(tramo_desnivel_m) / v_bajada
    else: return tiempo_llano
    return max(tiempo_llano, tiempo_desnivel)

def format_hours(hours_decimal):
    delta = datetime.timedelta(hours=hours_decimal)
    hours, remainder = divmod(delta.seconds, 3600)
    minutes, _ = divmod(remainder, 60)
    return f"{hours}h {minutes}m"

def segmentar_ruta_precisa(puntos, dist_minima_km):
    dists = [0.0]
    for i in range(1, len(puntos)):
        dists.append(dists[-1] + puntos[i-1].distance_2d(puntos[i])/1000.0)
    
    tramos = []
    i_inicio = 0
    while i_inicio < len(puntos) - 1:
        i_fin = len(puntos) - 1
        for j in range(i_inicio, len(puntos)):
            i_futuro = j
            while i_futuro < len(puntos) - 1 and dists[i_futuro] - dists[j] < dist_minima_km:
                i_futuro += 1
            des_act = puntos[j].elevation - puntos[i_inicio].elevation
            des_fut = puntos[i_futuro].elevation - puntos[j].elevation
            if des_act > 5 and des_fut < -5:
                elevaciones = [p.elevation for p in puntos[i_inicio:j+1]]
                i_fin = i_inicio + elevaciones.index(max(elevaciones))
                if i_fin > i_inicio: break
            elif des_act < -5 and des_fut > 5:
                elevaciones = [p.elevation for p in puntos[i_inicio:j+1]]
                i_fin = i_inicio + elevaciones.index(min(elevaciones))
                if i_fin > i_inicio: break
        
        if i_fin <= i_inicio: i_fin = len(puntos) - 1
        des_tot = puntos[i_fin].elevation - puntos[i_inicio].elevation
        tipo = 'subida' if des_tot > 5 else ('bajada' if des_tot < -5 else 'llano')
        tramos.append({'type': tipo, 'start_point_index': i_inicio, 'end_point_index': i_fin, 'dist': dists[i_fin] - dists[i_inicio], 'desnivel': des_tot})
        i_inicio = i_fin
        
    def fusionar(lista):
        fus = []
        if lista:
            fus.append(lista[0].copy())
            for t in lista[1:]:
                ult = fus[-1]
                if t['type'] == ult['type']:
                    ult['dist'] += t['dist']
                    ult['desnivel'] += t['desnivel']
                    ult['end_point_index'] = t['end_point_index']
                else: fus.append(t.copy())
        return fus

    tramos = fusionar(tramos)
    while True:
        if len(tramos) <= 1: break
        idx = next((i for i, t in enumerate(tramos) if t['dist'] < dist_minima_km), -1)
        if idx == -1: break 
        t_corto = tramos.pop(idx)
        if idx == 0:
            tramos[0]['dist'] += t_corto['dist']
            tramos[0]['desnivel'] += t_corto['desnivel']
            tramos[0]['start_point_index'] = t_corto['start_point_index']
        elif idx == len(tramos):
            tramos[-1]['dist'] += t_corto['dist']
            tramos[-1]['desnivel'] += t_corto['desnivel']
            tramos[-1]['end_point_index'] = t_corto['end_point_index']
        else:
            prev_t, next_t = tramos[idx - 1], tramos[idx]
            if prev_t['dist'] > next_t['dist']:
                prev_t['dist'] += t_corto['dist']
                prev_t['desnivel'] += t_corto['desnivel']
                prev_t['end_point_index'] = t_corto['end_point_index']
            else:
                next_t['dist'] += t_corto['dist']
                next_t['desnivel'] += t_corto['desnivel']
                next_t['start_point_index'] = t_corto['start_point_index']
        tramos = fusionar(tramos)
    return tramos

# --- 3. INTERFAZ ---
st.set_page_config(page_title="Generador Dossier Scout", layout="wide")
st.title("⚜️ Generador de Dossier de Rutas")

# Selectores automáticos
c1, c2 = st.columns(2)
rama = c1.selectbox("Rama", list(DATOS_RAMAS.keys()))
capacidad = c2.selectbox("Capacidad", ["muy baja", "baja", "media", "alta", "muy alta"], index=2)

v_h, v_a, v_d = DATOS_RAMAS[rama][capacidad]

# Panel lateral
st.sidebar.header("Ajustes Manuales")
v_plano = st.sidebar.number_input("Vel. Llano (km/h)", value=float(v_h))
v_subida = st.sidebar.number_input("Vel. Ascenso (m/h)", value=float(v_a))
v_bajada = st.sidebar.number_input("Vel. Descenso (m/h)", value=float(v_d))
dist_min = st.sidebar.number_input("Distancia Mín. (km)", value=0.3)

hora_salida = st.time_input("Hora de salida", datetime.time(9, 0))
archivo_gpx = st.file_uploader("Sube tu archivo .gpx", type=["gpx"])

if archivo_gpx is not None:
    gpx = gpxpy.parse(archivo_gpx)
    puntos = gpx.tracks[0].segments[0].points
    tramos = segmentar_ruta_precisa(puntos, dist_min)
    
    # --- GENERAR GRÁFICA ---
    elev = [p.elevation for p in puntos]
    dists_acum = [0.0]
    for i in range(1, len(puntos)):
        dists_acum.append(dists_acum[-1] + puntos[i-1].distance_2d(puntos[i]) / 1000.0)
        
    fig, ax = plt.subplots(figsize=(12, 4))
    colores = {'subida': 'red', 'bajada': 'green', 'llano': 'blue'}
    rango_elev = max(elev) - min(elev)
    offset = rango_elev * 0.10 

    for idx, seg in enumerate(tramos):
        inicio, fin = seg['start_point_index'], seg['end_point_index']
        ax.plot(dists_acum[inicio:fin+1], elev[inicio:fin+1], color=colores[seg['type']], linewidth=2)
        medio_idx = (inicio + fin) // 2
        ax.text(dists_acum[medio_idx], elev[medio_idx] + offset, str(idx + 1), 
                color='white', fontsize=10, fontweight='bold', ha='center', va='bottom',
                bbox=dict(boxstyle='circle,pad=0.3', fc='black', ec='none', alpha=0.7))

    ax.fill_between(dists_acum, elev, color='gray', alpha=0.1)
    ax.set_title(f"Perfil de Ruta: {rama} ({capacidad})")
    ax.set_xlabel("Distancia (km)")
    ax.set_ylabel("Elevación (m)")
    ax.grid(True, linestyle='--', alpha=0.6)
    plt.tight_layout()
    
    st.pyplot(fig)

    # --- BOTÓN DE DESCARGA (AÑADIDO) ---
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight")
    buf.seek(0)
    nombre_img = f"perfil_{archivo_gpx.name.replace('.gpx', '')}.png"
    
    st.download_button(
        label="📥 Descargar gráfica de perfil",
        data=buf,
        file_name=nombre_img,
        mime="image/png"
    )

    # --- TABLA DE DATOS ---
    total_hours = 0
    st.divider()
    for idx, seg in enumerate(tramos):
        time_h = calculate_time(seg['dist'], seg['desnivel'], seg['type'], v_plano, v_subida, v_bajada)
        total_hours += time_h
        pref = "+" if seg['desnivel'] > 0 else ""
        tipo = "(Subida)" if seg['type'] == 'subida' else ("(Bajada)" if seg['type'] == 'bajada' else "(Llano)")
        st.write(f"**Tramo {idx+1}** {tipo} | Distancia: {seg['dist']:.2f}km | Desnivel: {pref}{seg['desnivel']:.1f}m | Tiempo: {format_hours(time_h)}")

    # Horarios finales
    t_salida = datetime.timedelta(hours=hora_salida.hour, minutes=hora_salida.minute)
    t_llegada = t_salida + datetime.timedelta(hours=total_hours)
    llegada_h, rem = divmod(t_llegada.seconds, 3600)
    llegada_m, _ = divmod(rem, 60)
    st.success(f"**Tiempo total en ruta:** {format_hours(total_hours)} | **Llegada estimada:** {llegada_h:02d}:{llegada_m:02d}")
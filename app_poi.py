import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import datetime
import os
import base64

# ==========================================
# 0. PARCHE DE COMPATIBILIDAD
# ==========================================
if not hasattr(pd.DataFrame, 'iteritems'):
    pd.DataFrame.iteritems = pd.DataFrame.items
if not hasattr(pd.Series, 'iteritems'):
    pd.Series.iteritems = pd.Series.items

# ==========================================
# 1. CONFIGURACIÓN INICIAL
# ==========================================
st.set_page_config(page_title="Dashboard Físico POI", layout="wide", initial_sidebar_state="collapsed")

CACHE_FILE = "cache_poi_institucional.parquet"

# ==========================================
# 2. ENCABEZADO INSTITUCIONAL
# ==========================================
def get_base64_of_bin_file(bin_file):
    with open(bin_file, 'rb') as f:
        data = f.read()
    return base64.b64encode(data).decode()

logo_path = None
if os.path.exists("logo.png"):
    logo_path = "logo.png"
    mime_type = "image/png"
elif os.path.exists("logo.jpg"):
    logo_path = "logo.jpg"
    mime_type = "image/jpeg"

if logo_path:
    img_base64 = get_base64_of_bin_file(logo_path)
    img_html = f'<img src="data:{mime_type};base64,{img_base64}" style="height: 130px; margin-right: 20px;">'
else:
    img_html = ''

st.markdown(f"""
    <div style="background-color: #0A192F; padding: 8px 30px; border-radius: 8px; display: flex; align-items: center; justify-content: space-between; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
        <div>{img_html}</div>
        <div>
            <h2 style="color: #FFFFFF; margin: 0; text-align: right; font-family: 'Arial', sans-serif; font-size: 23px; font-weight: 600; letter-spacing: 0.5px;">
                OFICINA DE PLANEAMIENTO Y PROGRAMACIÓN MULTIANUAL DE INVERSIONES
            </h2>
        </div>
    </div>
""", unsafe_allow_html=True)

st.write("") 
st.divider()

# ==========================================
# 3. COORDENADAS GEOGRÁFICAS DEL PERÚ
# ==========================================
COORDENADAS_PERU = {
    'AMAZONAS': [-6.2316, -77.8690],
    'ANCASH': [-9.5277, -77.5287],
    'APURIMAC': [-14.0504, -72.9553],
    'AREQUIPA': [-16.4090, -71.5375],
    'AYACUCHO': [-13.1587, -74.2239],
    'CAJAMARCA': [-7.1638, -78.5003],
    'CALLAO': [-12.0566, -77.1181],
    'CUSCO': [-13.5383, -71.9675],
    'HUANCAVELICA': [-12.7865, -74.9727],
    'HUANUCO': [-9.9306, -76.2422],
    'ICA': [-14.0678, -75.7286],
    'JUNIN': [-12.0651, -75.2049],
    'LA LIBERTAD': [-8.1159, -79.0299],
    'LAMBAYEQUE': [-6.7714, -79.8409],
    'LIMA': [-12.0464, -77.0428],
    'LORETO': [-3.7491, -73.2538],
    'MADRE DE DIOS': [-12.5933, -70.4300],
    'MOQUEGUA': [-17.1983, -70.9356],
    'PASCO': [-10.6674, -76.2566],
    'PIURA': [-5.1945, -80.6328],
    'PUNO': [-15.8402, -70.0218],
    'SAN MARTIN': [-6.9038, -76.3377],
    'TACNA': [-18.0065, -70.2462],
    'TUMBES': [-3.5669, -80.4515],
    'UCAYALI': [-8.3791, -74.5539]
}

DEPARTAMENTOS_PERU = list(COORDENADAS_PERU.keys())

# Regiones institucionales que se muestran como UN SOLO PUNTO en Lima
REGIONES_CENTRALIZADAS = ['ANC (AUTORIDAD NACIONAL)', 'CARPETA FISCAL', 'IML (MEDICINA LEGAL)']

# ==========================================
# 4. FUNCIONES AUXILIARES
# ==========================================
def extraer_departamento_de_actividad(texto):
    if pd.isna(texto):
        return None
    texto = str(texto).upper().strip()
    if '-' in texto:
        parte_final = texto.split('-')[-1].strip()
        for depto in DEPARTAMENTOS_PERU:
            if depto in parte_final:
                return depto
    deptos_ordenados = sorted(DEPARTAMENTOS_PERU, key=len, reverse=True)
    for depto in deptos_ordenados:
        if depto in texto:
            return depto
    return None

def obtener_columna_ubigeo(df):
    for c in ['Ubigeo', 'UBIGEO', 'ubigeo', 'Código Ubigeo', 'Codigo Ubigeo', 'CODIGO UBIGEO']:
        if c in df.columns:
            return c
    return None

# ==========================================
# 5. LÓGICA DE CLASIFICACIÓN
# ==========================================
if 'region_seleccionada' not in st.session_state:
    st.session_state.region_seleccionada = None

def obtener_base_datos():
    if os.path.exists(CACHE_FILE):
        try:
            return pd.read_parquet(CACHE_FILE)
        except Exception:
            return None
    return None

def evaluar_semaforo(prog, ejec):
    if prog == 0 and ejec == 0: return '🟢 Verde (OK)'
    if prog == 0 and ejec > 0: return '🟣 Morado (Mala Prog.)'
    if prog > 0 and ejec == 0: return '🔴 Rojo (Crítico)'
    avance = (ejec / prog) * 100
    if avance > 125: return '🟣 Morado (Sobre-ejecución)'
    elif avance >= 90: return '🟢 Verde'
    elif avance >= 75: return '🟡 Amarillo'
    else: return '🔴 Rojo'

def detectar_falla_continua(row, mes_actual_num=9):
    fallas_consecutivas = 0
    for i in range(1, mes_actual_num + 1):
        mes_str = str(i).zfill(2)
        prog = row.get(f'F(RE) {mes_str}', 0)
        ejec = row.get(f'F(SE) {mes_str}', 0)
        if prog > 0:
            if (ejec / prog) < 0.75:
                fallas_consecutivas += 1
            else:
                fallas_consecutivas = 0 
        if fallas_consecutivas >= 3:
            return '🚨 SÍ'
    return 'NO'

def reclasificar_row(row):
    reg = str(row.get('Departamento Nombre UBIGEO', '')).upper().strip()
    prov = str(row.get('Provincia Nombre UBIGEO', '')).upper().strip()
    dist = str(row.get('Distrito Nombre UBIGEO', '')).upper().strip()
    ue = str(row.get('UE', '')).upper().strip()
    cc_resp = str(row.get('CC Responsable', '')).upper().strip()
    cc = str(row.get('Centro de Costo', '')).upper().strip()

    if ('CARPETA FISCAL' in ue or 'CARPETA FISCAL' in cc or 
        'CARPETA FISCAL' in cc_resp or 'CARPETA FISCAL' in reg or
        'CARPETA FISCAL ELECTRONICA' in ue or 'MULTIDEPARTAMENTAL' in reg or 'MULTIDEPARTAMENTAL' in ue):
        return 'CARPETA FISCAL'

    if ('MEDICINA LEGAL' in ue or 'IML' in ue or 
        'INSTITUTO DE MEDICINA LEGAL' in ue):
        return 'IML (MEDICINA LEGAL)'

    if ('AUTORIDAD NACIONAL' in ue or 'ANC' in ue):
        return 'ANC (AUTORIDAD NACIONAL)'

    if ('SULLANA' in prov or 'SULLANA' in dist or 
        'SULLANA' in cc_resp or 'SULLANA' in ue or 'SULLANA' in cc or 'SULLANA' in reg):
        return 'SULLANA'

    if 'PIURA' in reg or 'PIURA' in prov or 'PIURA' in ue:
        return 'PIURA'

    if reg == 'PROVINCIA CONSTITUCIONAL DEL CALLAO' or 'CALLAO' in reg:
        return 'CALLAO'
    
    if 'LIMA' in reg:
        return 'LIMA (GERENCIA GENERAL)'

    return reg

# ==========================================
# 6. PESTAÑAS
# ==========================================
tab_dash, tab_carga, tab_verificacion = st.tabs([
    "🗺️ Dashboard Ejecutivo", 
    "⚙️ Administrador (Carga de Datos)", 
    "✅ Verificación de Carga"
])

with tab_carga:
    st.header("Actualización de Base de Datos Institucional")
    st.info("Arrastra y suelta todos los archivos 'Exporta POI' (.xlsx) al mismo tiempo.")
    
    with st.form("form_carga"):
        archivos_subidos = st.file_uploader("Subir archivos .xlsx", type=['xlsx'], accept_multiple_files=True)
        submit_cargar = st.form_submit_button("Procesar y Guardar Archivos", type="primary")
        
    if submit_cargar:
        if archivos_subidos:
            with st.spinner("Procesando..."):
                lista_dfs = []
                for archivo in archivos_subidos:
                    df_temp = pd.read_excel(archivo)
                    df_temp['Archivo_Origen'] = archivo.name
                    lista_dfs.append(df_temp)
                
                df = pd.concat(lista_dfs, ignore_index=True)
                
                meses = [str(i).zfill(2) for i in range(1, 13)]
                cols_re = [f'F(RE) {m}' for m in meses] + ['F(RE) Total']
                cols_se = [f'F(SE) {m}' for m in meses] + ['F(SE) Total']
                
                for col in cols_re + cols_se:
                    if col in df.columns:
                        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
                
                df['Alerta_Critica_3M'] = df.apply(lambda row: detectar_falla_continua(row, 9), axis=1)
                df['Region_Filtro'] = df.apply(reclasificar_row, axis=1)
                
                def obtener_departamento_real(row):
                    depto_original = str(row.get('Departamento Nombre UBIGEO', '')).upper().strip()
                    actividad = row.get('Actividad Operativa', '')
                    depto_extraido = extraer_departamento_de_actividad(actividad)
                    if depto_extraido:
                        return depto_extraido
                    return depto_original
                
                df['Departamento_Real'] = df.apply(obtener_departamento_real, axis=1)
                
                df.to_parquet(CACHE_FILE, index=False)
                st.success(f"✅ ¡Éxito! Se guardaron {len(df)} registros de {len(archivos_subidos)} archivos.")
        else:
            st.warning("⚠️ Debes seleccionar al menos un archivo Excel.")

with tab_verificacion:
    st.header("✅ Verificación de Carga")
    st.caption("Comprueba que todos los archivos se cargaron correctamente en la base de datos.")
    
    df_diag = obtener_base_datos()
    if df_diag is None:
        st.warning("⚠️ No hay datos cargados. Sube los archivos en la pestaña 'Administrador'.")
    else:
        st.subheader("📋 Regiones Detectadas")
        regiones = df_diag['Region_Filtro'].value_counts().reset_index()
        regiones.columns = ['Region_Filtro', 'Cantidad de Registros']
        st.dataframe(regiones, use_container_width=True)
        
        st.subheader("🗺️ Departamentos Reales Detectados")
        if 'Departamento_Real' in df_diag.columns:
            deptos = df_diag['Departamento_Real'].value_counts().reset_index()
            deptos.columns = ['Departamento_Real', 'Cantidad de Registros']
            st.dataframe(deptos, use_container_width=True)
        
        st.subheader("🔍 Detalle IML (Departamento extraído de Actividad Operativa)")
        df_iml = df_diag[df_diag['Region_Filtro'] == 'IML (MEDICINA LEGAL)']
        if len(df_iml) > 0:
            cols_show = [c for c in ['Archivo_Origen', 'UE', 'Actividad Operativa', 'Departamento Nombre UBIGEO', 'Departamento_Real'] if c in df_iml.columns]
            st.dataframe(df_iml[cols_show], use_container_width=True)
        else:
            st.info("No hay registros de IML en los datos cargados.")

with tab_dash:
    fecha_actual = datetime.datetime.now().strftime('%d/%m/%Y')
    st.markdown(f"<div style='text-align: right; font-size: 15px; color: #666;'><b>Fecha de consulta:</b> {fecha_actual}</div>", unsafe_allow_html=True)
    
    df_cargado = obtener_base_datos()
    
    if df_cargado is None:
        st.warning("⚠️ No hay base de datos. Sube los archivos en 'Administrador'.")
    else:
        st.success(f"📂 **Base de Datos Activa:** {len(df_cargado):,} registros.")

        df_base = df_cargado.copy()
        df_base['Region_Filtro'] = df_base.apply(reclasificar_row, axis=1)
        
        def obtener_departamento_real(row):
            depto_original = str(row.get('Departamento Nombre UBIGEO', '')).upper().strip()
            actividad = row.get('Actividad Operativa', '')
            depto_extraido = extraer_departamento_de_actividad(actividad)
            if depto_extraido:
                return depto_extraido
            return depto_original
        
        df_base['Departamento_Real'] = df_base.apply(obtener_departamento_real, axis=1)
        
        col_filtro1, col_filtro2 = st.columns(2)
        meses_dict = {"Enero": "01", "Febrero": "02", "Marzo": "03", "Abril": "04", 
                      "Mayo": "05", "Junio": "06", "Julio": "07", "Agosto": "08", 
                      "Septiembre": "09", "Octubre": "10", "Noviembre": "11", "Diciembre": "12"}
                      
        with col_filtro1:
            vista = st.radio("Período:", ["Acumulado (Enero - Mes elegido)", "Mes Específico (Individual)"], horizontal=True)
            
        with col_filtro2:
            mes_sel = st.selectbox("Mes de corte:", list(meses_dict.keys()), index=8)
            mes_num = int(meses_dict[mes_sel])
            
            if vista == "Mes Específico (Individual)":
                col_prog = f"F(RE) {meses_dict[mes_sel]}"
                col_ejec = f"F(SE) {meses_dict[mes_sel]}"
            else:
                col_prog = 'Prog_Acumulada'
                col_ejec = 'Ejec_Acumulada'
                columnas_prog_acum = [f'F(RE) {str(i).zfill(2)}' for i in range(1, mes_num + 1)]
                columnas_ejec_acum = [f'F(SE) {str(i).zfill(2)}' for i in range(1, mes_num + 1)]
                df_base[col_prog] = df_base[columnas_prog_acum].sum(axis=1)
                df_base[col_ejec] = df_base[columnas_ejec_acum].sum(axis=1)

        if vista == "Mes Específico (Individual)":
            st.info(f"📌 **Datos Individuales:** {mes_sel}.")
        else:
            st.info(f"📌 **Datos Acumulados:** Enero - {mes_sel}.")

        df_base['Estado_Semaforo'] = df_base.apply(lambda row: evaluar_semaforo(row[col_prog], row[col_ejec]), axis=1)
        df_base['Avance_%'] = np.where(df_base[col_prog] > 0, (df_base[col_ejec] / df_base[col_prog]) * 100, 0)
        df_base['Avance_%'] = df_base['Avance_%'].clip(upper=999) 

        st.divider()

        st.markdown("""
            <div style="background-color: #f8fafc; padding: 12px 20px; border-radius: 8px; border-left: 6px solid #0A192F; margin-bottom: 20px;">
                <span style="font-size: 15px; color: #334155;">
                    <b>📊 LEYENDA:</b> &nbsp;
                    🟢 <b>Óptimo:</b> 90-125% &nbsp;|&nbsp;
                    🟡 <b>En Riesgo:</b> 75-89% &nbsp;|&nbsp;
                    🔴 <b>Crítico:</b> <75% &nbsp;|&nbsp;
                    🟣 <b>Sobre-ejecución:</b> >125% &nbsp;|&nbsp;
                    🚨 <b>Alerta:</b> 3+ meses en Rojo
                </span>
            </div>
        """, unsafe_allow_html=True)

        # =========================================================
        # MAPA NACIONAL BLINDADO
        # =========================================================
        if st.session_state.region_seleccionada is None:
            opciones_regiones = ["-- Seleccione una región --"] + sorted([r for r in df_base['Region_Filtro'].dropna().unique()])
            region_elegida = st.selectbox("🔎 **Ingrese a una región o distrito fiscal:**", opciones_regiones)
            
            if region_elegida != "-- Seleccione una región --":
                st.session_state.region_seleccionada = region_elegida
                st.rerun()
            
            df_base['Avance_Para_Promedio'] = df_base['Avance_%'].clip(upper=125)

            # --- Regiones Centralizadas ---
            df_centralizadas = df_base[df_base['Region_Filtro'].isin(REGIONES_CENTRALIZADAS)].copy()
            if len(df_centralizadas) > 0:
                df_centralizadas_mapa = df_centralizadas.groupby('Region_Filtro').agg({'Avance_Para_Promedio': 'mean'}).reset_index()
                df_centralizadas_mapa.rename(columns={'Avance_Para_Promedio': 'Avance_%'}, inplace=True)
                df_centralizadas_mapa['Latitud'] = -12.0464
                df_centralizadas_mapa['Longitud'] = -77.0428
                df_centralizadas_mapa['Texto_Region'] = df_centralizadas_mapa['Region_Filtro']
                df_centralizadas_mapa['Departamento_Real'] = 'LIMA'
            else:
                df_centralizadas_mapa = pd.DataFrame(columns=['Region_Filtro','Avance_%','Latitud','Longitud','Texto_Region','Departamento_Real'])

            # --- Resto de regiones ---
            df_resto = df_base[~df_base['Region_Filtro'].isin(REGIONES_CENTRALIZADAS)].copy()
            df_mapa_resto = df_resto.groupby(['Region_Filtro', 'Departamento_Real']).agg({'Avance_Para_Promedio': 'mean'}).reset_index()
            df_mapa_resto.rename(columns={'Avance_Para_Promedio': 'Avance_%'}, inplace=True)

            # FUNCIÓN ROBUSTA DE COORDENADAS PARA EVITAR EL BUG DE LA SELVA
            def obtener_coords(row):
                reg = str(row.get('Region_Filtro', '')).upper().strip()
                depto = str(row.get('Departamento_Real', '')).upper().strip()
                
                # 1. Fuerza bruta a las entidades con nombre específico
                if reg == 'SULLANA' or 'SULLANA' in reg: return -4.90, -80.68
                if reg == 'PIURA' or 'PIURA' in reg: return -5.19, -80.63
                if 'CALLAO' in reg or 'CALLAO' in depto: return -12.0566, -77.1181
                if 'LIMA' in reg: return -12.0464, -77.0428
                
                # 2. Búsqueda exacta en el diccionario por Departamento
                if depto in COORDENADAS_PERU:
                    return COORDENADAS_PERU[depto][0], COORDENADAS_PERU[depto][1]
                
                # 3. Búsqueda exacta en el diccionario por Región
                if reg in COORDENADAS_PERU:
                    return COORDENADAS_PERU[reg][0], COORDENADAS_PERU[reg][1]
                
                # 4. Búsqueda parcial (por si viene con espacios como 'ANCASH ' o 'PASCO ')
                for key, coords in COORDENADAS_PERU.items():
                    if key in depto or key in reg:
                        return coords[0], coords[1]
                
                # 5. Si todo falla, en vez de enviarlos a la selva, los mandamos a Lima (Sede central)
                return -12.0464, -77.0428

            if len(df_mapa_resto) > 0:
                coords = df_mapa_resto.apply(obtener_coords, axis=1, result_type='expand')
                df_mapa_resto['Latitud'] = coords[0]
                df_mapa_resto['Longitud'] = coords[1]
                
                # Limpiar texto para el mapa
                def limpiar_texto(nombre):
                    if nombre == 'LIMA (GERENCIA GENERAL)': return 'GERENCIA GENERAL'
                    return nombre
                
                df_mapa_resto['Texto_Region'] = df_mapa_resto['Region_Filtro'].apply(limpiar_texto)

            # Unir todo
            df_mapa = pd.concat([df_mapa_resto, df_centralizadas_mapa], ignore_index=True)
            df_mapa['Color'] = df_mapa['Avance_%'].apply(lambda x: 'purple' if x > 125 else ('green' if x >= 90 else ('orange' if x >= 75 else 'red')))

            config_mapa = {'scrollZoom': False, 'doubleClick': False, 'displayModeBar': False}

            # --- MAPA: ventana compacta y encuadrada ---
            try:
                fig = px.scatter_map(
                    df_mapa, lat="Latitud", lon="Longitud", 
                    text="Texto_Region", hover_name="Texto_Region", 
                    hover_data={"Avance_%": ':.1f', "Region_Filtro": False, "Departamento_Real": False, "Latitud": False, "Longitud": False, "Color": False, "Texto_Region": False},
                    color="Color", color_discrete_map={'green': '#00cc66', 'orange': '#ffaa00', 'red': '#ff3333', 'purple': '#9333ea'},
                    zoom=4.5, center={"lat": -9.3, "lon": -75.0} # Zoom y centro perfeccionados para Perú
                )
                fig.update_traces(marker=dict(size=12, opacity=0.9), textposition='top right', textfont=dict(size=11, color='black', family="Arial", weight="bold"))
                fig.update_layout(
                    map_style="open-street-map", 
                    showlegend=False, 
                    height=500,
                    margin={"r":0,"t":0,"l":0,"b":0}
                )
            except AttributeError:
                fig = px.scatter_mapbox(
                    df_mapa, lat="Latitud", lon="Longitud", 
                    text="Texto_Region", hover_name="Texto_Region", 
                    hover_data={"Avance_%": ':.1f', "Region_Filtro": False, "Departamento_Real": False, "Latitud": False, "Longitud": False, "Color": False, "Texto_Region": False},
                    color="Color", color_discrete_map={'green': '#00cc66', 'orange': '#ffaa00', 'red': '#ff3333', 'purple': '#9333ea'},
                    zoom=4.5, center={"lat": -9.3, "lon": -75.0}
                )
                fig.update_traces(marker=dict(size=12, opacity=0.9), textposition='top right', textfont=dict(size=11, color='black', family="Arial", weight="bold"))
                fig.update_layout(
                    mapbox_style="open-street-map", 
                    showlegend=False, 
                    height=500,
                    margin={"r":0,"t":0,"l":0,"b":0}
                )
            
            st.plotly_chart(fig, use_container_width=True, config=config_mapa)

        # =========================================================
        # DETALLE DE REGIÓN
        # =========================================================
        else:
            region = st.session_state.region_seleccionada
            
            if st.button("⬅️ Volver al Mapa Nacional", type="primary"):
                st.session_state.region_seleccionada = None
                st.rerun()
                
            st.markdown(f"<h2 style='color: #0A192F; font-size: 32px; font-weight: 800; margin-bottom: 20px;'>🔍 Detalle Operativo: {region}</h2>", unsafe_allow_html=True)
            
            df_region = df_base[df_base['Region_Filtro'] == region]
            
            if region in REGIONES_CENTRALIZADAS:
                deptos = ["Todos"] + sorted(list(df_region['Departamento_Real'].dropna().unique()))
                depto_sel = st.selectbox("Filtrar por Departamento:", deptos)
                if depto_sel != "Todos":
                    df_region = df_region[df_region['Departamento_Real'] == depto_sel]
            
            ues = ["Todas"] + list(df_region['UE'].unique())
            ue_sel = st.selectbox("Filtrar por Unidad Ejecutora:", ues)
            
            if ue_sel != "Todas":
                df_region = df_region[df_region['UE'] == ue_sel]

            col_ubigeo = obtener_columna_ubigeo(df_region)

            df_problemas = df_region[(df_region['Estado_Semaforo'].str.contains('Rojo')) | (df_region['Estado_Semaforo'].str.contains('Morado')) | (df_region['Alerta_Critica_3M'] == '🚨 SÍ')]
            
            cols_mostrar = ['UE', 'Centro de Costo']
            if col_ubigeo:
                cols_mostrar.append(col_ubigeo)
            cols_mostrar += ['Unidad de Medida', col_prog, col_ejec, 'Estado_Semaforo', 'Alerta_Critica_3M']
            
            df_problemas_visual = df_problemas[cols_mostrar].rename(columns={'Alerta_Critica_3M': 'Alerta Crítica (3+ meses)'})
            
            st.markdown("### 🚨 Centros de Costo Críticos")
            st.dataframe(df_problemas_visual.reset_index(drop=True), use_container_width=True, height=400)
            
            st.markdown("### 📈 Seguimiento de Avance Mensual (%)")
            
            nombres_meses_cortos = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']
            
            base_cols = ['UE', 'Centro de Costo']
            if col_ubigeo:
                base_cols.append(col_ubigeo)
            base_cols.append('Unidad de Medida')
            
            df_seguimiento = df_region[base_cols].copy()
            
            for i in range(1, 13):
                m_str = str(i).zfill(2)
                col_p = f'F(RE) {m_str}'
                col_e = f'F(SE) {m_str}'
                
                if col_p in df_region.columns and col_e in df_region.columns:
                    prog_val = df_region[col_p]
                    ejec_val = df_region[col_e]
                    lista_mes = []
                    for p, e in zip(prog_val, ejec_val):
                        if p > 0:
                            avance = round((e / p) * 100, 1)
                            lista_mes.append(f"{avance}%")
                        elif p == 0 and e > 0:
                            e_str = f"{int(e)}" if e == int(e) else f"{e:.1f}"
                            lista_mes.append(f"🟣 {e_str} (Sin meta)")
                        else:
                            lista_mes.append("-")
                    df_seguimiento[nombres_meses_cortos[i-1]] = lista_mes
                else:
                    df_seguimiento[nombres_meses_cortos[i-1]] = "-"

            st.dataframe(df_seguimiento.reset_index(drop=True), use_container_width=True, height=500)
            
            df_region_completa = df_region[cols_mostrar].rename(columns={'Alerta_Critica_3M': 'Alerta Crítica (3+ meses)'})
            with st.expander("Ver sabana completa"):
                st.dataframe(df_region_completa.reset_index(drop=True), use_container_width=True, height=500)

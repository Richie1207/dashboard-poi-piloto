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
# 3. LÓGICA
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

# ==========================================
# 4. PESTAÑAS
# ==========================================
tab_dash, tab_carga, tab_diagnostico = st.tabs(["🗺️ Dashboard Ejecutivo", "⚙️ Administrador (Carga de Datos)", "🔍 Diagnóstico"])

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
                
                # =====================================================
                # CLASIFICACIÓN DE REGIONES (CORREGIDA)
                # =====================================================
                def definir_region_filtro(row):
                    reg = str(row.get('Departamento Nombre UBIGEO', '')).upper()
                    prov = str(row.get('Provincia Nombre UBIGEO', '')).upper()
                    dist = str(row.get('Distrito Nombre UBIGEO', '')).upper()
                    ue = str(row.get('UE', '')).upper()
                    cc_resp = str(row.get('CC Responsable', '')).upper()
                    cc = str(row.get('Centro de Costo', '')).upper()
                    
                    # 1. CARPETA FISCAL (incluye MULTIDEPARTAMENTAL)
                    if ('CARPETA FISCAL' in reg or 'CARPETA FISCAL' in ue or 
                        'CARPETA FISCAL' in cc or 'CARPETA FISCAL' in cc_resp or
                        'MULTIDEPARTAMENTAL' in reg or 'MULTIDEPARTAMENTAL' in ue):
                        return 'CARPETA FISCAL'
                    
                    # 2. Callao
                    elif reg == 'PROVINCIA CONSTITUCIONAL DEL CALLAO':
                        return 'CALLAO'
                    
                    # 3. Lima
                    elif 'LIMA' in reg:
                        if 'MEDICINA LEGAL' in ue: return 'LIMA (IML)'
                        elif 'AUTORIDAD NACIONAL' in ue: return 'LIMA (ANC)'
                        else: return 'LIMA (GERENCIA GENERAL)'
                    
                    # 4. SULLANA (PRIORIDAD ALTA - antes que Piura)
                    elif ('SULLANA' in prov or 'SULLANA' in dist or 
                          'SULLANA' in cc_resp or 'SULLANA' in ue or 'SULLANA' in cc):
                        return 'SULLANA'
                    
                    # 5. PIURA (solo si no es Sullana)
                    elif 'PIURA' in reg or 'PIURA' in prov or 'PIURA' in ue:
                        return 'PIURA'
                    
                    else:
                        return reg
                
                df['Region_Filtro'] = df.apply(definir_region_filtro, axis=1)
                
                # Diagnóstico: mostrar cuántos registros tiene cada región
                conteo = df['Region_Filtro'].value_counts()
                st.write("**Regiones detectadas después de la clasificación:**")
                st.dataframe(conteo.reset_index().rename(columns={'index': 'Región', 'Region_Filtro': 'Cantidad'}), use_container_width=True)
                
                df.to_parquet(CACHE_FILE, index=False)
                st.success(f"✅ ¡Éxito! Se guardaron {len(df)} registros de {len(archivos_subidos)} archivos.")
        else:
            st.warning("⚠️ Debes seleccionar al menos un archivo Excel.")

with tab_diagnostico:
    st.header("🔍 Diagnóstico de Datos")
    df_diag = obtener_base_datos()
    if df_diag is None:
        st.warning("⚠️ No hay datos cargados.")
    else:
        st.subheader("📋 Regiones Detectadas")
        regiones = df_diag['Region_Filtro'].value_counts().reset_index()
        regiones.columns = ['Region_Filtro', 'Cantidad']
        st.dataframe(regiones, use_container_width=True)
        
        st.subheader("🔎 ¿Existe SULLANA en los datos?")
        if st.button("Buscar SULLANA"):
            df_sullana = df_diag[
                df_diag.apply(lambda row: 'SULLANA' in ' '.join([str(v).upper() for v in row.values if pd.notna(v)]), axis=1)
            ]
            if len(df_sullana) > 0:
                st.success(f"✅ Se encontraron {len(df_sullana)} registros con 'SULLANA'.")
                cols_show = [c for c in ['Archivo_Origen', 'UE', 'CC Responsable', 'Centro de Costo', 'Provincia Nombre UBIGEO', 'Distrito Nombre UBIGEO', 'Region_Filtro'] if c in df_sullana.columns]
                st.dataframe(df_sullana[cols_show].head(20), use_container_width=True)
            else:
                st.error("❌ NO existe 'SULLANA' en los datos cargados.")
        
        st.subheader("🔎 Registros clasificados como SULLANA")
        if 'Region_Filtro' in df_diag.columns:
            df_s = df_diag[df_diag['Region_Filtro'] == 'SULLANA']
            if len(df_s) > 0:
                st.success(f"✅ Hay {len(df_s)} registros clasificados como SULLANA.")
                cols_show = [c for c in ['Archivo_Origen', 'UE', 'CC Responsable', 'Centro de Costo', 'Provincia Nombre UBIGEO', 'Region_Filtro'] if c in df_s.columns]
                st.dataframe(df_s[cols_show].head(20), use_container_width=True)
            else:
                st.warning("⚠️ No hay registros clasificados como SULLANA. Revisa la clasificación.")

with tab_dash:
    fecha_actual = datetime.datetime.now().strftime('%d/%m/%Y')
    st.markdown(f"<div style='text-align: right; font-size: 15px; color: #666;'><b>Fecha de consulta:</b> {fecha_actual}</div>", unsafe_allow_html=True)
    
    df_cargado = obtener_base_datos()
    
    if df_cargado is None:
        st.warning("⚠️ No hay base de datos. Sube los archivos en 'Administrador'.")
    else:
        st.success(f"📂 **Base de Datos Activa:** {len(df_cargado):,} registros.")

        df_base = df_cargado.copy()
        df_base['Region_Filtro'] = df_base['Region_Filtro'].replace('MULTIDEPARTAMENTAL', 'CARPETA FISCAL')
        
        # FORZAR separación de Sullana si aún está dentro de PIURA
        # Si hay registros con "SULLANA" en alguna columna pero clasificados como PIURA, reclasificar
        mask_sullana = df_base.apply(
            lambda row: 'SULLANA' in ' '.join([str(v).upper() for v in row.values if pd.notna(v)]), axis=1
        )
        df_base.loc[mask_sullana, 'Region_Filtro'] = 'SULLANA'
        
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
        # MAPA NACIONAL
        # =========================================================
        if st.session_state.region_seleccionada is None:
            opciones_regiones = ["-- Seleccione una región --"] + sorted([r for r in df_base['Region_Filtro'].dropna().unique()])
            region_elegida = st.selectbox("🔎 **Ingrese a una región o distrito fiscal:**", opciones_regiones)
            
            if region_elegida != "-- Seleccione una región --":
                st.session_state.region_seleccionada = region_elegida
                st.rerun()
            
            df_base['Avance_Para_Promedio'] = df_base['Avance_%'].clip(upper=125)
            df_mapa = df_base.groupby(['Departamento Nombre UBIGEO', 'UE', 'Region_Filtro']).agg({'Avance_Para_Promedio': 'mean'}).reset_index()
            df_mapa.rename(columns={'Avance_Para_Promedio': 'Avance_%'}, inplace=True)
            
            coordenadas_peru = {
                'AMAZONAS': [-6.2316, -77.8690], 'ANCASH': [-9.5277, -77.5287], 'APURIMAC': [-14.0504, -72.9553], 
                'AREQUIPA': [-15.8402, -72.2530], 'AYACUCHO': [-13.1587, -74.2239], 'CAJAMARCA': [-6.2294, -78.4727],
                'CUSCO': [-13.5383, -71.9675], 'HUANCAVELICA': [-12.7865, -74.9727], 'HUANUCO': [-9.9306, -76.2422], 
                'ICA': [-14.0722, -75.7335], 'JUNIN': [-11.1588, -75.9922], 'LA LIBERTAD': [-8.1159, -79.0299], 
                'LAMBAYEQUE': [-6.4255, -79.8800], 'LORETO': [-3.7491, -73.2538], 'MADRE DE DIOS': [-12.5933, -70.4300], 
                'MOQUEGUA': [-17.1983, -70.9356], 'PASCO': [-10.6674, -76.2566], 'PIURA': [-5.19, -80.63], 
                'PUNO': [-15.8402, -70.0218], 'SAN MARTIN': [-6.9038, -76.3377], 'TACNA': [-18.0065, -70.2462], 
                'TUMBES': [-3.5669, -80.4515], 'UCAYALI': [-8.3791, -74.5539]
            }

            def obtener_lat(row):
                reg = row['Region_Filtro']
                if 'LIMA (IML)' in reg: return -11.60
                elif 'LIMA (ANC)' in reg: return -11.95
                elif 'LIMA (GERENCIA GENERAL)' in reg: return -12.05
                elif 'CALLAO' in reg: return -12.06
                elif 'SULLANA' in reg: return -4.90
                elif 'PIURA' in reg: return -5.19
                elif 'CARPETA FISCAL' in reg: return -12.04
                else: return coordenadas_peru.get(str(row['Departamento Nombre UBIGEO']).upper(), [0, 0])[0]

            def obtener_lon(row):
                reg = row['Region_Filtro']
                if 'LIMA (IML)' in reg: return -76.60
                elif 'LIMA (ANC)' in reg: return -76.30
                elif 'LIMA (GERENCIA GENERAL)' in reg: return -76.90
                elif 'CALLAO' in reg: return -77.15
                elif 'SULLANA' in reg: return -80.68
                elif 'PIURA' in reg: return -80.63
                elif 'CARPETA FISCAL' in reg: return -77.03
                else: return coordenadas_peru.get(str(row['Departamento Nombre UBIGEO']).upper(), [0, 0])[1]

            def limpiar_nombre(reg_filtro):
                if 'LIMA (' in reg_filtro:
                    return reg_filtro.replace('LIMA (', '').replace(')', '')
                return reg_filtro

            df_mapa['Latitud'] = df_mapa.apply(obtener_lat, axis=1)
            df_mapa['Longitud'] = df_mapa.apply(obtener_lon, axis=1)
            df_mapa['Texto_Region'] = df_mapa['Region_Filtro'].apply(limpiar_nombre)
            df_mapa['Color'] = df_mapa['Avance_%'].apply(lambda x: 'purple' if x > 125 else ('green' if x >= 90 else ('orange' if x >= 75 else 'red')))

            config_mapa = {'scrollZoom': False, 'doubleClick': False, 'displayModeBar': False}

            try:
                fig = px.scatter_map(
                    df_mapa, lat="Latitud", lon="Longitud", 
                    text="Texto_Region", hover_name="Region_Filtro", 
                    hover_data={"Avance_%": ':.1f', "Departamento Nombre UBIGEO": False, "Region_Filtro": False, "Latitud": False, "Longitud": False, "Color": False, "Texto_Region": False},
                    color="Color", color_discrete_map={'green': '#00cc66', 'orange': '#ffaa00', 'red': '#ff3333', 'purple': '#9333ea'},
                    zoom=4.6, center={"lat": -9.3, "lon": -75.0}
                )
                fig.update_traces(marker=dict(size=13, opacity=0.9), textposition='top right', textfont=dict(size=12, color='black', family="Arial", weight="bold"))
                fig.update_layout(map_style="open-street-map", showlegend=False, height=580, margin={"r":0,"t":0,"l":0,"b":0}, map_bounds={"west": -85.0, "east": -65.0, "south": -20.0, "north": 0.0})
            except AttributeError:
                fig = px.scatter_mapbox(
                    df_mapa, lat="Latitud", lon="Longitud", 
                    text="Texto_Region", hover_name="Region_Filtro", 
                    hover_data={"Avance_%": ':.1f', "Departamento Nombre UBIGEO": False, "Region_Filtro": False, "Latitud": False, "Longitud": False, "Color": False, "Texto_Region": False},
                    color="Color", color_discrete_map={'green': '#00cc66', 'orange': '#ffaa00', 'red': '#ff3333', 'purple': '#9333ea'},
                    zoom=4.6, center={"lat": -9.3, "lon": -75.0}
                )
                fig.update_traces(marker=dict(size=13, opacity=0.9), textposition='top right', textfont=dict(size=12, color='black', family="Arial", weight="bold"))
                fig.update_layout(mapbox_style="open-street-map", showlegend=False, height=580, margin={"r":0,"t":0,"l":0,"b":0}, mapbox_bounds={"west": -85.0, "east": -65.0, "south": -20.0, "north": 0.0})
            
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
            
            ues = ["Todas"] + list(df_region['UE'].unique())
            ue_sel = st.selectbox("Filtrar por Unidad Ejecutora:", ues)
            
            if ue_sel != "Todas":
                df_region = df_region[df_region['UE'] == ue_sel]
            
            df_problemas = df_region[(df_region['Estado_Semaforo'].str.contains('Rojo')) | (df_region['Estado_Semaforo'].str.contains('Morado')) | (df_region['Alerta_Critica_3M'] == '🚨 SÍ')]
            cols_mostrar = ['UE', 'Centro de Costo', 'Unidad de Medida', col_prog, col_ejec, 'Estado_Semaforo', 'Alerta_Critica_3M']
            
            df_problemas_visual = df_problemas[cols_mostrar].rename(columns={'Alerta_Critica_3M': 'Alerta Crítica (3+ meses)'})
            df_region_completa = df_region[cols_mostrar].rename(columns={'Alerta_Critica_3M': 'Alerta Crítica (3+ meses)'})
            
            st.markdown("### 🚨 Centros de Costo Críticos")
            st.dataframe(df_problemas_visual.reset_index(drop=True), use_container_width=True, height=400)
            
            st.markdown("### 📈 Seguimiento de Avance Mensual (%)")
            
            nombres_meses_cortos = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']
            df_seguimiento = df_region[['UE', 'Centro de Costo', 'Unidad de Medida']].copy()
            
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
            
            with st.expander("Ver sabana completa"):
                st.dataframe(df_region_completa.reset_index(drop=True), use_container_width=True, height=500)

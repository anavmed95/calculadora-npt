import streamlit as st
import pdfplumber
import pandas as pd
import re
import math
from io import BytesIO
from datetime import datetime

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Consolidador NPT & OC Semanal", page_icon="🏥", layout="wide")

# --- BASE DE DATOS INTERNA DE CÓDIGOS SAP ---
DATA_NPT_RANGOS = [
    {"min": 0, "max": 250, "sap": "10050679", "desc": "NUTRICION PARENTERAL NEO (0 - 250 ML). UNIDAD 1 UNI"},
    {"min": 251, "max": 500, "sap": "10050687", "desc": "NUTRICION PARENTERAL NEO (251 - 500 ML)"},
    {"min": 501, "max": 1000, "sap": "10050688", "desc": "NUTRICION PARENTERAL NEO (501 - 1000 ML)"},
    {"min": 1001, "max": 2000, "sap": "10001680", "desc": "NUTRICION PARENT.1001-2000ML (MAGISTRAL)"},
    {"min": 2001, "max": 4000, "sap": "10001680", "desc": "NUTRICION PARENT.2001-4000ML (MAGISTRAL)"}
]

DATA_ADITIVOS = [
    {"key": "OMEGAVEN", "sap": "10050677", "desc": "NUTRICION PARENTERAL C/OMEGAVEN 10%100M. UNIDAD 1 UNI", "vol_frasco": 100},
    {"key": "DIPEPTIVEN", "sap": "10001681", "desc": "DIPEPTIVEN 100ML EN NUTRICION PARENTERAL", "vol_frasco": 100}
]

def limpiar_num(t):
    if not t: return 0.0
    n = t.replace('.', '').replace(',', '.')
    try: return float(n)
    except: return 0.0

def extraer_fecha(texto):
    # Busca patrones como: FECHA INDICACION : 08-08-2026 o FECHA : 08/08/2026
    m_fecha = re.search(r"FECHA\s*(?:INDICACIÓN|INDICACION)?\s*:\s*(\d{2}[-/\.]\d{2}[-/\.]\d{4})", texto, re.IGNORECASE)
    if m_fecha:
        str_f = m_fecha.group(1).replace('/', '-').replace('.', '-')
        try:
            return datetime.strptime(str_f, "%d-%m-%Y")
        except:
            pass
    return datetime.today()

st.title("🏥 Consolidador de NPT - Gestión de Órdenes de Compra Semanales")
st.markdown("Sube los archivos PDF individuales o agrupados por días/semana para calcular el total necesario para SAP.")

uploaded_files = st.file_uploader("Selecciona los archivos PDF de las Recetas", type="pdf", accept_multiple_files=True)

if uploaded_files:
    registros = []
    
    for uploaded_file in uploaded_files:
        with pdfplumber.open(uploaded_file) as pdf:
            texto_completo = ""
            for page in pdf.pages:
                texto_completo += (page.extract_text() or "") + "\n"
        
        # 1. Extracción de Fecha y Semana
        fecha_receta = extraer_fecha(texto_completo)
        num_semana = f"Semana {fecha_receta.isocalendar()[1]} ({fecha_receta.year})"
        fecha_str = fecha_receta.strftime("%Y-%m-%d")

        # 2. Extracción de Paciente / RUT (Opcional para trazabilidad)
        m_pac = re.search(r"PACIENTE\s*:\s*([^\n]+)", texto_completo, re.IGNORECASE)
        nombre_paciente = m_pac.group(1).strip() if m_pac else uploaded_file.name

        # 3. Lógica de Volumen Total
        v_final_bolsa = 0.0
        m_v_final = re.search(r"V\.\s*Total\s*NP\s*\+\s*adicional\s*\(mL\)\s+([\d,.]+)", texto_completo, re.IGNORECASE)
        
        if m_v_final:
            v_final_bolsa = limpiar_num(m_v_final.group(1))
        else:
            m_v_simple = re.search(r"Volumen Total NP \(mL\)\s+([\d,.]+)", texto_completo)
            if m_v_simple:
                v_final_bolsa = limpiar_num(m_v_simple.group(1))
            else:
                m_peso = re.search(r"PESO\s*:\s*([\d,.]+)\s*(kg|gr)", texto_completo, re.IGNORECASE)
                m_v_kg = re.search(r"Volumen Total NP \(ml/Kg/día\)\s+([\d,.]+)", texto_completo)
                if m_peso and m_v_kg:
                    val_peso = limpiar_num(m_peso.group(1))
                    unidad_p = m_peso.group(2).lower()
                    peso = val_peso if unidad_p == "kg" else val_peso / 1000.0
                    v_final_bolsa = limpiar_num(m_v_kg.group(1)) * peso

        # Clasificación por bolsa principal
        if v_final_bolsa > 0:
            for r in DATA_NPT_RANGOS:
                if v_final_bolsa > r["min"] and v_final_bolsa <= r["max"]:
                    registros.append({
                        "FECHA": fecha_str,
                        "SEMANA": num_semana,
                        "PACIENTE": nombre_paciente,
                        "SAP": r["sap"],
                        "DESC": r["desc"],
                        "CANT": 1
                    })
                    break

        # 4. Lógica de Aditivos (Omegaven / Dipeptiven)
        lineas = texto_completo.split('\n')
        for adi in DATA_ADITIVOS:
            for linea in lineas:
                if adi["key"] in linea.upper() and len(linea) < 150:
                    tokens = re.findall(r"[\d,.]+%?", linea)
                    nums_limpios = [t for t in tokens if '%' not in t]
                    valores = [limpiar_num(n) for n in nums_limpios if limpiar_num(n) > 5]
                    if valores:
                        v_adi = valores[-1]
                        frascos = math.ceil(v_adi / adi["vol_frasco"])
                        registros.append({
                            "FECHA": fecha_str,
                            "SEMANA": num_semana,
                            "PACIENTE": nombre_paciente,
                            "SAP": adi["sap"],
                            "DESC": adi["desc"],
                            "CANT": int(frascos)
                        })
                        break

    if registros:
        df_raw = pd.DataFrame(registros)
        
        tab1, tab2 = st.tabs(["📄 Resumen del Lote Subido", "🛒 Consolidado Semanal para Orden de Compra (OC)"])

        with tab1:
            st.subheader("Listado Procesado")
            df_lote = df_raw.groupby(['SAP', 'DESC'])['CANT'].sum().reset_index()
            st.dataframe(df_lote, use_container_width=True)

        with tab2:
            st.subheader("📊 Consolidado Semanal Acumulado (Para OC)")
            
            # Selector de Semana si hay varias fechas procesadas
            semanas_disponibles = df_raw['SEMANA'].unique()
            semana_sel = st.selectbox("Selecciona la semana de análisis:", semanas_disponibles)
            
            df_semana = df_raw[df_raw['SEMANA'] == semana_sel]
            
            # Agrupación semanal final
            df_oc = df_semana.groupby(['SAP', 'DESC'])['CANT'].sum().reset_index()
            df_oc.rename(columns={'CANT': 'CANTIDAD TOTAL SEMANA'}, inplace=True)
            
            st.metric("Total de Ítems / Unidades NPT en la Semana", int(df_oc['CANTIDAD TOTAL SEMANA'].sum()))
            st.dataframe(df_oc, use_container_width=True)

            # Exportar Excel Semanal
            output_oc = BytesIO()
            with pd.ExcelWriter(output_oc, engine='openpyxl') as writer:
                df_oc.to_excel(writer, index=False, sheet_name="OC Semanal NPT")
                df_raw.to_excel(writer, index=False, sheet_name="Detalle Diario Recetas")
            
            st.download_button(
                label="📥 Descargar Reporte Semanal para Orden de Compra (.XLSX)",
                data=output_oc.getvalue(),
                file_name=f"OC_Semanal_NPT_{semana_sel.replace(' ', '_')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

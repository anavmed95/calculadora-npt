import streamlit as st
import pdfplumber
import pandas as pd
import re
import math
from io import BytesIO

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Consolidador NPT Farmacia", page_icon="🏥")

# --- BASE DE DATOS INTERNA ---
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

st.title("🏥 Consolidador de Nutriciones Parenterales")
st.write("Sube los PDFs de las recetas para generar el consolidado SAP.")

uploaded_files = st.file_uploader("Selecciona los archivos PDF", type="pdf", accept_multiple_files=True)

if uploaded_files:
    resultados = []
    for uploaded_file in uploaded_files:
        with pdfplumber.open(uploaded_file) as pdf:
            texto_completo = ""
            for page in pdf.pages:
                texto_completo += (page.extract_text() or "") + "\n"
        
        # LÓGICA DE VOLUMEN TOTAL
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

        if v_final_bolsa > 0:
            for r in DATA_NPT_RANGOS:
                if v_final_bolsa > r["min"] and v_final_bolsa <= r["max"]:
                    resultados.append({"SAP": r["sap"], "DESC": r["desc"], "CANT": 1})
                    break

        # LÓGICA DE ADITIVOS
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
                        resultados.append({"SAP": adi["sap"], "DESC": adi["desc"], "CANT": int(frascos)})
                        break

    if resultados:
        df_final = pd.DataFrame(resultados).groupby(['SAP', 'DESC'])['CANT'].sum().reset_index()
        st.success("✅ Procesado con éxito")
        st.dataframe(df_final)

        # Botón de descarga Excel
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df_final.to_excel(writer, index=False)
        st.download_button(label="📥 Descargar Excel para SAP", data=output.getvalue(), file_name="consolidado_npt.xlsx")

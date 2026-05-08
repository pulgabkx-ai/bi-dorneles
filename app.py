import streamlit as st
import pandas as pd
import plotly.express as px
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import time

# 1. CONFIGURAÇÃO DA PÁGINA
st.set_page_config(page_title="BI Dorneles Soluções", layout="wide", page_icon="📊")

# 2. CONEXÃO COM TRATAMENTO DE ASSINATURA (JWT)
@st.cache_resource
def conectar_google_sheets():
    escopos = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    
    try:
        # Carrega os segredos do painel do Streamlit
        info_chaves = dict(st.secrets["gcp_service_account"])
        
        # --- LIMPEZA DE ASSINATURA ---
        if "private_key" in info_chaves:
            pk = info_chaves["private_key"]
            # Remove aspas residuais e espaços nas extremidades
            pk = pk.strip().strip('"').strip("'")
            # Converte a sequência literal \n em quebras de linha reais
            pk = pk.replace("\\n", "\n")
            info_chaves["private_key"] = pk

        # Usa o endpoint mais estável do Google
        info_chaves["token_uri"] = "https://accounts.google.com/o/oauth2/token"
            
        creds = Credentials.from_service_account_info(info_chaves, scopes=escopos)
        client = gspread.authorize(creds)
        
        url_da_planilha = "https://docs.google.com/spreadsheets/d/18XXK_Wqz2Stb_dFDb5sfl-u9W0B5kHqioc3Ar1xK2Is/edit"
        return client.open_by_url(url_da_planilha).sheet1
        
    except Exception as e:
        st.error(f"Erro de Autenticação (JWT): {e}")
        st.stop()

@st.cache_data(ttl=60)
def buscar_e_limpar_dados():
    aba = conectar_google_sheets()
    df = pd.DataFrame(aba.get_all_records())
    df.columns = df.columns.str.strip()
    
    # Tratamento de Moeda
    colunas_moeda = ['Valor Estimado', 'Valor Final', 'Custo Frete']
    for col in colunas_moeda:
        if col in df.columns:
            df[col] = pd.to_numeric(
                df[col].astype(str).str.replace(r'[R\$\s\.]', '', regex=True).str.replace(',', '.'), 
                errors='coerce'
            ).fillna(0)
    
    # Tratamento de Datas
    df['Data de Entrada'] = pd.to_datetime(df['Data de Entrada'], dayfirst=True, errors='coerce')
    return df

# Inicialização do App
try:
    df_base = buscar_e_limpar_dados()
except Exception as e:
    st.error(f"Erro ao processar dados: {e}")
    st.stop()

# 3. INTERFACE SIMPLIFICADA
st.title("📊 BI Dorneles Soluções")

# Resumo rápido para confirmar que funcionou
m1, m2, m3 = st.columns(3)
m1.metric("Total de Leads", len(df_base))
m2.metric("Valor Orçado", f"R$ {df_base['Valor Estimado'].sum():,.2f}")
m3.metric("Faturamento", f"R$ {df_base[df_base['Status'].str.lower() == 'fechado']['Valor Final'].sum():,.2f}")

st.subheader("Visualização dos Dados")
st.dataframe(df_base, use_container_width=True)

st.caption(f"Sincronizado em: {datetime.now().strftime('%d/%m/%Y %H:%M')}")

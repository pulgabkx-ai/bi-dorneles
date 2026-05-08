import streamlit as st
import pandas as pd
import plotly.express as px
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import time

# 1. CONFIGURAÇÃO DA PÁGINA
st.set_page_config(page_title="BI Dorneles Soluções", layout="wide", page_icon="📊")

# 2. FUNÇÃO DE CONEXÃO (Ajustada para evitar o KeyError)
@st.cache_resource
def conectar_google_sheets():
    # Verifica se a seção principal existe
    if "gcp_service_account" not in st.secrets:
        st.error("ERRO: A seção [gcp_service_account] não existe nos Secrets do Streamlit.")
        st.info("Vá em Settings > Secrets e verifique se a primeira linha é [gcp_service_account]")
        st.stop()

    info_chaves = dict(st.secrets["gcp_service_account"])
    escopos = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    
    try:
        # Limpeza da chave privada para evitar erro de assinatura JWT
        if "private_key" in info_chaves:
            pk = info_chaves["private_key"].strip().strip('"').strip("'")
            info_chaves["private_key"] = pk.replace("\\n", "\n")
        else:
            st.error("ERRO: O campo 'private_key' não foi encontrado dentro de [gcp_service_account].")
            st.stop()

        # Força o endpoint estável
        info_chaves["token_uri"] = "https://accounts.google.com/o/oauth2/token"
            
        creds = Credentials.from_service_account_info(info_chaves, scopes=escopos)
        client = gspread.authorize(creds)
        
        url_da_planilha = "https://docs.google.com/spreadsheets/d/18XXK_Wqz2Stb_dFDb5sfl-u9W0B5kHqioc3Ar1xK2Is/edit"
        return client.open_by_url(url_da_planilha).sheet1
        
    except Exception as e:
        st.error(f"Erro de Autenticação: {e}")
        st.stop()

@st.cache_data(ttl=60)
def buscar_e_limpar_dados():
    aba = conectar_google_sheets()
    df = pd.DataFrame(aba.get_all_records())
    
    if df.empty:
        return df

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

# Fluxo Principal
try:
    df_base = buscar_e_limpar_dados()
    
    if df_base.empty:
        st.warning("Planilha conectada, mas nenhum dado foi encontrado.")
        st.stop()

    # 3. INTERFACE DO DASHBOARD
    st.title("📊 BI Dorneles Soluções")
    
    # Filtros simples
    colunas = df_base.columns.tolist()
    if 'Operador' in colunas:
        sel_op = st.sidebar.multiselect("Operadores", options=sorted(df_base['Operador'].unique()), default=sorted(df_base['Operador'].unique()))
        df_f = df_base[df_base['Operador'].isin(sel_op)]
    else:
        df_f = df_base

    # Métricas
    m1, m2 = st.columns(2)
    m1.metric("Leads Totais", len(df_f))
    if 'Valor Estimado' in df_f.columns:
        m2.metric("Total Orçado", f"R$ {df_f['Valor Estimado'].sum():,.2f}")

    st.subheader("Visualização dos Dados")
    st.dataframe(df_f, use_container_width=True)

except Exception as e:
    st.error(f"Erro ao carregar o dashboard: {e}")

st.caption(f"Última tentativa de sincronização: {datetime.now().strftime('%d/%m/%Y %H:%M')}")

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
        # Carrega dos Secrets
        info_chaves = dict(st.secrets["gcp_service_account"])
        
        # LIMPEZA CRÍTICA DA CHAVE: Resolve o erro 'Invalid JWT Signature'
        if "private_key" in info_chaves:
            # Remove aspas extras, espaços e garante as quebras de linha corretas
            key = info_chaves["private_key"].strip()
            if "\\n" in key:
                key = key.replace("\\n", "\n")
            info_chaves["private_key"] = key

        # Força o endpoint estável
        info_chaves["token_uri"] = "https://accounts.google.com/o/oauth2/token"
            
        creds = Credentials.from_service_account_info(info_chaves, scopes=escopos)
        client = gspread.authorize(creds)
        
        url_da_planilha = "https://docs.google.com/spreadsheets/d/18XXK_Wqz2Stb_dFDb5sfl-u9W0B5kHqioc3Ar1xK2Is/edit"
        return client.open_by_url(url_da_planilha).sheet1
        
    except Exception as e:
        st.error(f"Erro de Autenticação (JWT): {e}")
        st.info("Dica: Verifique se a 'private_key' nos Secrets começa com '-----BEGIN PRIVATE KEY-----' e termina corretamente.")
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
    df['Dias em Processo'] = (datetime.now() - df['Data de Entrada']).dt.days.fillna(0).astype(int)
    return df

# Inicialização
try:
    df_base = buscar_e_limpar_dados()
except Exception as e:
    st.error(f"Erro ao processar dados: {e}")
    st.stop()

# 3. DASHBOARD SIMPLIFICADO (Para teste de carga)
st.title("📊 BI Dorneles Soluções")
st.sidebar.header("🎯 Filtros")

# Filtros
sel_op = st.sidebar.multiselect("Operadores", options=sorted(df_base['Operador'].unique()), default=sorted(df_base['Operador'].unique()))
df_f = df_base[df_base['Operador'].isin(sel_op)]

m1, m2 = st.columns(2)
m1.metric("Total Orçado", f"R$ {df_f['Valor Estimado'].sum():,.2f}")
m2.metric("Faturamento", f"R$ {df_f[df_f['Status'].str.lower() == 'fechado']['Valor Final'].sum():,.2f}")

st.subheader("📋 Base de Dados Atualizada")
st.dataframe(df_f, use_container_width=True)

st.caption(f"Última atualização: {datetime.now().strftime('%d/%m/%Y %H:%M')}")

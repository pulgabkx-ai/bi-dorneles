import streamlit as st
import pandas as pd
import plotly.express as px
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import time

# 1. CONFIGURAÇÃO DA PÁGINA
st.set_page_config(page_title="BI Dorneles Soluções", layout="wide", page_icon="📊")

# 2. CONEXÃO ESTÁVEL
@st.cache_resource
def conectar_google_sheets():
    escopos = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    
    if "gcp_service_account" not in st.secrets:
        st.error("Erro: Seção [gcp_service_account] não encontrada nos Secrets.")
        st.stop()

    try:
        info_chaves = dict(st.secrets["gcp_service_account"])
        
        # Limpeza da chave privada para evitar erro JWT
        if "private_key" in info_chaves:
            pk = info_chaves["private_key"].strip().strip('"').strip("'")
            info_chaves["private_key"] = pk.replace("\\n", "\n")
        
        info_chaves["token_uri"] = "https://accounts.google.com/o/oauth2/token"
            
        creds = Credentials.from_service_account_info(info_chaves, scopes=escopos)
        client = gspread.authorize(creds)
        
        url_da_planilha = "https://docs.google.com/spreadsheets/d/18XXK_Wqz2Stb_dFDb5sfl-u9W0B5kHqioc3Ar1xK2Is/edit"
        return client.open_by_url(url_da_planilha).sheet1
        
    except Exception as e:
        st.error(f"Falha na conexão: {e}")
        st.stop()

# 3. TRATAMENTO DE DADOS COM PROTEÇÃO CONTRA KEYERROR
@st.cache_data(ttl=60)
def buscar_e_limpar_dados():
    aba = conectar_google_sheets()
    dados = aba.get_all_records()
    
    if not dados:
        return pd.DataFrame()
        
    df = pd.DataFrame(dados)
    
    # Limpa espaços em branco nos nomes das colunas (causa comum de KeyError)
    df.columns = [str(col).strip() for col in df.columns]
    
    # Lista de colunas obrigatórias para o BI não quebrar
    colunas_necessarias = ['Status', 'Valor Estimado', 'Valor Final', 'Custo Frete', 'Operador', 'Data de Entrada']
    for col in colunas_necessarias:
        if col not in df.columns:
            df[col] = 0 if 'Valor' in col or 'Custo' in col else "N/A"

    # Conversão de Moeda
    colunas_moeda = ['Valor Estimado', 'Valor Final', 'Custo Frete']
    for col in colunas_moeda:
        df[col] = pd.to_numeric(
            df[col].astype(str).str.replace(r'[R\$\s\.]', '', regex=True).str.replace(',', '.'), 
            errors='coerce'
        ).fillna(0)
    
    # Conversão de Datas
    df['Data de Entrada'] = pd.to_datetime(df['Data de Entrada'], dayfirst=True, errors='coerce')
    df = df[df['Data de Entrada'].notna()]
    
    return df

# --- CARREGAMENTO ---
try:
    df_base = buscar_e_limpar_dados()
except Exception as e:
    st.error(f"Erro ao processar dados: {e}")
    st.stop()

# 4. INTERFACE E FILTROS
st.title("📊 BI Dorneles Soluções")
st.sidebar.header("🎯 Filtros")

# Filtro de Data
data_min = df_base['Data de Entrada'].min().to_pydatetime()
data_max = df_base['Data de Entrada'].max().to_pydatetime()
periodo = st.sidebar.date_input("Período de Entrada", value=(data_min, data_max))

# Filtros de Multiselect
sel_op = st.sidebar.multiselect("Operadores", options=sorted(df_base['Operador'].unique()), default=sorted(df_base['Operador'].unique()))
sel_st = st.sidebar.multiselect("Status", options=sorted(df_base['Status'].unique()), default=sorted(df_base['Status'].unique()))

# Aplicação dos Filtros
df_f = df_base.copy()
if len(periodo) == 2:
    df_f = df_f[(df_f['Data de Entrada'].dt.date >= periodo[0]) & (df_f['Data de Entrada'].dt.date <= periodo[1])]

df_f = df_f[(df_f['Operador'].isin(sel_op)) & (df_f['Status'].isin(sel_st))]

# 5. LAYOUT COM PROTEÇÃO DE CÁLCULO
tab1, tab2 = st.tabs(["🚀 Visão Geral", "🔍 Detalhes"])

with tab1:
    c1, c2, c3 = st.columns(3)
    
    # Cálculos seguros usando .get() ou checagem de existência
    v_orcado = df_f['Valor Estimado'].sum() if 'Valor Estimado' in df_f.columns else 0
    
    # Correção do Erro: Checagem antes de filtrar por Status
    if 'Status' in df_f.columns and 'Valor Final' in df_f.columns:
        v_fechado = df_f[df_f['Status'].astype(str).str.lower() == 'fechado']['Valor Final'].sum()
    else:
        v_fechado = 0
        
    v_frete = df_f['Custo Frete'].sum() if 'Custo Frete' in df_f.columns else 0
    
    c1.metric("Total Orçado", f"R$ {v_orcado:,.2f}")
    c2.metric("Total Fechado", f"R$ {v_fechado:,.2f}")
    c3.metric("Custo Frete", f"R$ {v_frete:,.2f}")

    st.divider()

    col_g1, col_g2 = st.columns(2)
    with col_g1:
        st.subheader("Funil de Vendas")
        df_funnel = df_f.groupby('Status')['Valor Estimado'].sum().reset_index().sort_values('Valor Estimado', ascending=False)
        st.plotly_chart(px.funnel(df_funnel, y='Status', x='Valor Estimado', color='Status'), use_container_width=True)

    with col_g2:
        st.subheader("Faturamento por Operador")
        df_op = df_f.groupby('Operador')['Valor Final'].sum().reset_index()
        st.plotly_chart(px.bar(df_op, x='Operador', y='Valor Final', text_auto='.2s'), use_container_width=True)

with tab2:
    st.dataframe(df_f, use_container_width=True, hide_index=True)

st.caption(f"Sincronizado em: {datetime.now().strftime('%d/%m/%Y %H:%M')}")

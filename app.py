import streamlit as st
import pandas as pd
import plotly.express as px
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import time

# 1. CONFIGURAÇÃO DA PÁGINA
st.set_page_config(page_title="BI Dorneles Soluções", layout="wide", page_icon="📊")

# 2. CONEXÃO BLINDADA
@st.cache_resource
def conectar_google_sheets():
    escopos = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    
    # Tentativas de conexão com tempo de espera
    for tentativa in range(5):
        try:
            # Puxa dos Secrets
            info_chaves = dict(st.secrets["gcp_service_account"])
            
            # Garante que a private_key está formatada corretamente
            if "private_key" in info_chaves:
                info_chaves["private_key"] = info_chaves["private_key"].replace("\\n", "\n")
            
            # Tenta forçar o endpoint mais estável se o DNS estiver falhando
            info_chaves["token_uri"] = "https://accounts.google.com/o/oauth2/token"
                
            creds = Credentials.from_service_account_info(info_chaves, scopes=escopos)
            client = gspread.authorize(creds)
            
            url_da_planilha = "https://docs.google.com/spreadsheets/d/18XXK_Wqz2Stb_dFDb5sfl-u9W0B5kHqioc3Ar1xK2Is/edit"
            return client.open_by_url(url_da_planilha).sheet1
            
        except Exception as e:
            if tentativa < 4:
                time.sleep(5) # Dá 5 segundos para o DNS do servidor "acordar"
                continue
            else:
                st.error(f"Erro Crítico de Rede (DNS): {e}")
                st.stop()

@st.cache_data(ttl=60)
def buscar_e_limpar_dados():
    aba = conectar_google_sheets()
    dados = aba.get_all_records()
    if not dados:
        return pd.DataFrame()
        
    df = pd.DataFrame(dados)
    df.columns = df.columns.str.strip()
    
    # Conversão de Moeda
    colunas_moeda = ['Valor Estimado', 'Valor Final', 'Custo Frete']
    for col in colunas_moeda:
        if col in df.columns:
            df[col] = pd.to_numeric(
                df[col].astype(str).str.replace(r'[R\$\s\.]', '', regex=True).str.replace(',', '.'), 
                errors='coerce'
            ).fillna(0)
    
    # Conversão de Datas
    df['Data de Entrada'] = pd.to_datetime(df['Data de Entrada'], dayfirst=True, errors='coerce')
    df['Dias em Processo'] = (datetime.now() - df['Data de Entrada']).dt.days.fillna(0).astype(int)
    return df

# Inicialização segura
try:
    df_base = buscar_e_limpar_dados()
    if df_base.empty:
        st.warning("A planilha parece estar vazia.")
        st.stop()
except Exception as e:
    st.error(f"Falha ao carregar planilha: {e}")
    st.stop()

# 3. FILTROS LATERAIS
st.sidebar.header("🎯 Filtros")
data_min = df_base['Data de Entrada'].min().to_pydatetime()
data_max = df_base['Data de Entrada'].max().to_pydatetime()
periodo = st.sidebar.date_input("Período", value=(data_min, data_max))

def criar_multiselect(titulo, coluna):
    opcoes = sorted(df_base[coluna].unique().tolist())
    return st.sidebar.multiselect(titulo, options=opcoes, default=opcoes)

sel_op = criar_multiselect("Operadores", "Operador")
sel_st = criar_multiselect("Status", "Status")

# 4. APLICAÇÃO DOS FILTROS
df_f = df_base.copy()
if len(periodo) == 2:
    df_f = df_f[(df_f['Data de Entrada'].dt.date >= periodo[0]) & (df_f['Data de Entrada'].dt.date <= periodo[1])]
df_f = df_f[(df_f['Operador'].isin(sel_op)) & (df_f['Status'].isin(sel_st))]

# 5. DASHBOARD
st.title("📊 BI Dorneles Soluções")
tab1, tab2 = st.tabs(["🚀 Visão Geral", "🔍 Detalhes"])

with tab1:
    col_m1, col_m2, col_m3 = st.columns(3)
    total_est = df_f['Valor Estimado'].sum()
    total_fat = df_f[df_f['Status'].str.lower() == 'fechado']['Valor Final'].sum()
    
    col_m1.metric("Orçado", f"R$ {total_est:,.2f}")
    col_m2.metric("Fechado", f"R$ {total_fat:,.2f}")
    col_m3.metric("Frete Total", f"R$ {df_f['Custo Frete'].sum():,.2f}")

    # Gráfico de Funil
    df_funnel = df_f.groupby('Status')['Valor Estimado'].sum().reset_index().sort_values('Valor Estimado', ascending=False)
    fig = px.funnel(df_funnel, y='Status', x='Valor Estimado', color='Status')
    st.plotly_chart(fig, use_container_width=True)

with tab2:
    st.dataframe(df_f, use_container_width=True, hide_index=True)

st.caption(f"Sincronizado em: {datetime.now().strftime('%d/%m/%Y %H:%M')}")

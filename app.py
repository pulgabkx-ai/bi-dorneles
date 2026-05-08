import streamlit as st
import pandas as pd
import plotly.express as px
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import time

# 1. CONFIGURAÇÃO DA PÁGINA
st.set_page_config(page_title="BI Dorneles Soluções", layout="wide", page_icon="📊")

# 2. CONEXÃO ESTÁVEL (A "Bala de Prata" que funcionou)
@st.cache_resource
def conectar_google_sheets():
    escopos = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    
    if "gcp_service_account" not in st.secrets:
        st.error("Erro: Seção [gcp_service_account] não encontrada nos Secrets.")
        st.stop()

    try:
        info_chaves = dict(st.secrets["gcp_service_account"])
        
        # Limpeza profunda da chave privada para evitar erro JWT
        if "private_key" in info_chaves:
            pk = info_chaves["private_key"].strip().strip('"').strip("'")
            info_chaves["private_key"] = pk.replace("\\n", "\n")
        
        # Uso do endpoint mais robusto do Google
        info_chaves["token_uri"] = "https://accounts.google.com/o/oauth2/token"
            
        creds = Credentials.from_service_account_info(info_chaves, scopes=escopos)
        client = gspread.authorize(creds)
        
        # URL da Planilha Dorneles Soluções
        url_da_planilha = "https://docs.google.com/spreadsheets/d/18XXK_Wqz2Stb_dFDb5sfl-u9W0B5kHqioc3Ar1xK2Is/edit"
        return client.open_by_url(url_da_planilha).sheet1
        
    except Exception as e:
        st.error(f"Falha na conexão estável: {e}")
        st.stop()

# 3. TRATAMENTO DE DADOS COMPLETO
@st.cache_data(ttl=60)
def buscar_e_limpar_dados():
    aba = conectar_google_sheets()
    dados = aba.get_all_records()
    
    if not dados:
        return pd.DataFrame()
        
    df = pd.DataFrame(dados)
    df.columns = df.columns.str.strip()
    
    # Conversão de Moeda (Lógica Original)
    colunas_moeda = ['Valor Estimado', 'Valor Final', 'Custo Frete']
    for col in colunas_moeda:
        if col in df.columns:
            df[col] = pd.to_numeric(
                df[col].astype(str).str.replace(r'[R\$\s\.]', '', regex=True).str.replace(',', '.'), 
                errors='coerce'
            ).fillna(0)
    
    # Conversão de Datas
    if 'Data de Entrada' in df.columns:
        df['Data de Entrada'] = pd.to_datetime(df['Data de Entrada'], dayfirst=True, errors='coerce')
        # Filtra datas inválidas (NaT) para não quebrar o slider
        df = df[df['Data de Entrada'].notna()]
    
    return df

# --- CARREGAMENTO INICIAL ---
try:
    df_base = buscar_e_limpar_dados()
    if df_base.empty:
        st.warning("A planilha está vazia ou não pôde ser lida.")
        st.stop()
except Exception as e:
    st.error(f"Erro ao processar dados: {e}")
    st.stop()

# 4. DASHBOARD COMPLETO (FILTROS E GRÁFICOS)
st.title("📊 BI Dorneles Soluções")

# Sidebar - Filtros
st.sidebar.header("🎯 Filtros")

# Filtro de Data dinâmico
data_min = df_base['Data de Entrada'].min().to_pydatetime()
data_max = df_base['Data de Entrada'].max().to_pydatetime()
periodo = st.sidebar.date_input("Período de Entrada", value=(data_min, data_max))

# Filtros de Multiselect
def criar_filtro(titulo, coluna):
    opcoes = sorted(df_base[coluna].dropna().unique().tolist())
    return st.sidebar.multiselect(titulo, options=opcoes, default=opcoes)

sel_op = criar_filtro("Operadores", "Operador")
sel_st = criar_filtro("Status", "Status")

# Aplicação dos Filtros
df_f = df_base.copy()
if len(periodo) == 2:
    df_f = df_f[(df_f['Data de Entrada'].dt.date >= periodo[0]) & (df_f['Data de Entrada'].dt.date <= periodo[1])]

df_f = df_f[(df_f['Operador'].isin(sel_op)) & (df_f['Status'].isin(sel_st))]

# 5. LAYOUT DE MÉTRICAS E GRÁFICOS
tab1, tab2 = st.tabs(["🚀 Visão Geral", "🔍 Detalhes da Base"])

with tab1:
    # Métricas Principais
    col_m1, col_m2, col_m3 = st.columns(3)
    
    v_orcado = df_f['Valor Estimado'].sum()
    v_fechado = df_f[df_f['Status'].str.lower() == 'fechado']['Valor Final'].sum()
    v_frete = df_f['Custo Frete'].sum()
    
    col_m1.metric("Total Orçado", f"R$ {v_orcado:,.2f}")
    col_m2.metric("Total Fechado", f"R$ {v_fechado:,.2f}", delta=f"{len(df_f[df_f['Status'].str.lower() == 'fechado'])} negócios")
    col_m3.metric("Custo Frete", f"R$ {v_frete:,.2f}")

    st.divider()

    # Gráficos
    col_g1, col_g2 = st.columns(2)

    with col_g1:
        st.subheader("Funil de Vendas (Status)")
        df_funnel = df_f.groupby('Status')['Valor Estimado'].sum().reset_index().sort_values('Valor Estimado', ascending=False)
        fig_funnel = px.funnel(df_funnel, y='Status', x='Valor Estimado', color='Status', 
                               color_discrete_sequence=px.colors.qualitative.Prism)
        st.plotly_chart(fig_funnel, use_container_width=True)

    with col_g2:
        st.subheader("Performance por Operador")
        df_op = df_f.groupby('Operador')['Valor Final'].sum().reset_index()
        fig_bar = px.bar(df_op, x='Operador', y='Valor Final', text_auto='.2s',
                         title="Valor Final Fechado por Operador")
        st.plotly_chart(fig_bar, use_container_width=True)

with tab2:
    st.subheader("Tabela de Dados Filtrada")
    st.dataframe(df_f, use_container_width=True, hide_index=True)
    
    # Botão de Download
    csv = df_f.to_csv(index=False).encode('utf-8')
    st.download_button("📥 Baixar CSV Filtrado", data=csv, file_name="bi_dorneles_export.csv", mime="text/csv")

st.caption(f"Sincronizado em: {datetime.now().strftime('%d/%m/%Y %H:%M')}")

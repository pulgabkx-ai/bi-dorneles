import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta

# --- 1. CONFIGURAÇÃO ---
st.set_page_config(page_title="BI Dorneles Soluções", layout="wide", page_icon="📊")

# Função auxiliar para formatar moeda no padrão BR
def formatar_moeda(valor):
    """Formata float para string R$ 1.234,56"""
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

# --- 2. CONEXÃO E DADOS ---
@st.cache_resource
def conectar_google_sheets():
    escopos = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    if "gcp_service_account" in st.secrets:
        info = dict(st.secrets["gcp_service_account"])
        if "private_key" in info:
            info["private_key"] = info["private_key"].strip().strip('"').strip("'").replace("\\n", "\n")
        info["token_uri"] = "https://accounts.google.com/o/oauth2/token"
        creds = Credentials.from_service_account_info(info, scopes=escopos)
    else:
        creds = Credentials.from_service_account_file('credenciais-dorneles.json', scopes=escopos)
    client = gspread.authorize(creds)
    return client.open_by_url("https://docs.google.com/spreadsheets/d/18XXK_Wqz2Stb_dFDb5sfl-u9W0B5kHqioc3Ar1xK2Is/edit").sheet1

@st.cache_data(ttl=60)
def buscar_e_limpar_dados():
    aba = conectar_google_sheets()
    df = pd.DataFrame(aba.get_all_records())
    if df.empty: return df
    df.columns = [str(col).strip() for col in df.columns]
    
    # Tratamento de Moeda vindo da planilha
    for col in ['Valor Estimado', 'Valor Final', 'Custo Frete']:
        df[col] = pd.to_numeric(df[col].astype(str).str.replace(r'[R\$\s\.]', '', regex=True).str.replace(',', '.'), errors='coerce').fillna(0)
    
    df['Data de Entrada'] = pd.to_datetime(df['Data de Entrada'], dayfirst=True, errors='coerce')
    df = df.dropna(subset=['Data de Entrada'])
    df['Dias em Processo'] = (datetime.now() - df['Data de Entrada']).dt.days.fillna(0).astype(int)
    return df

# --- 3. LÓGICA E FILTROS ---
df_base = buscar_e_limpar_dados()
if df_base.empty: st.stop()

st.sidebar.header("🎯 Painel de Controle")
meta = st.sidebar.number_input("Meta Mensal (R$)", value=50000.0, step=1000.0)
periodo = st.sidebar.date_input("Período", value=(df_base['Data de Entrada'].min().to_pydatetime(), df_base['Data de Entrada'].max().to_pydatetime()))

sel_op = st.sidebar.multiselect("Operadores", sorted(df_base['Operador'].unique()), default=sorted(df_base['Operador'].unique()))
sel_st = st.sidebar.multiselect("Status", sorted(df_base['Status'].unique()), default=sorted(df_base['Status'].unique()))

df_f = df_base.copy()
if isinstance(periodo, (list, tuple)) and len(periodo) == 2:
    df_f = df_f[(df_f['Data de Entrada'].dt.date >= periodo[0]) & (df_f['Data de Entrada'].dt.date <= periodo[1])]

df_f = df_f[(df_f['Operador'].isin(sel_op)) & (df_f['Status'].isin(sel_st))]

# --- 4. DASHBOARD ---
st.title("📊 BI Dorneles Soluções")

tab1, tab2 = st.tabs(["🚀 Visão Geral", "📈 Performance"])

with tab1:
    m1, m2, m3, m4 = st.columns(4)
    v_orc = df_f['Valor Estimado'].sum()
    v_real = df_f[df_f['Status'].str.lower() == 'fechado']['Valor Final'].sum()
    
    # Exibição com formatador de moeda BR
    m1.metric("Orçado", formatar_moeda(v_orc))
    m2.metric("Faturamento", formatar_moeda(v_real))
    m3.metric("Frete Total", formatar_moeda(df_f['Custo Frete'].sum()))
    m4.metric("Leads", len(df_f))

    # Radar Estratégico (WOW) com Moeda formatada
    st.divider()
    cw1, cw2 = st.columns([1, 2])
    with cw1:
        fig_gauge = go.Figure(go.Indicator(
            mode = "gauge+number",
            value = v_real,
            title = {'text': "Progresso da Meta"},
            gauge = {'axis': {'range': [None, meta]}, 'bar': {'color': "#1C83E1"}}))
        fig_gauge.update_layout(height=250)
        st.plotly_chart(fig_gauge, use_container_width=True)

    with cw2:
        df_sankey = df_f.groupby(['Operador', 'Status'])['Valor Estimado'].sum().reset_index()
        nodes = list(pd.concat([df_sankey['Operador'], df_sankey['Status']]).unique())
        node_dict = {name: i for i, name in enumerate(nodes)}
        fig_sankey = go.Figure(data=[go.Sankey(
            node = dict(pad=15, thickness=20, label=nodes, color="#1C83E1"),
            link = dict(source=df_sankey['Operador'].map(node_dict), target=df_sankey['Status'].map(node_dict), value=df_sankey['Valor Estimado']))])
        fig_sankey.update_layout(height=250, margin=dict(l=0,r=0,t=20,b=0))
        st.plotly_chart(fig_sankey, use_container_width=True)

    st.subheader("📋 Detalhes dos Leads")
    # Formatação visual para a tabela
    df_display = df_f.copy()
    for col in ['Valor Estimado', 'Valor Final', 'Custo Frete']:
        df_display[col] = df_display[col].apply(formatar_moeda)
    st.dataframe(df_display, use_container_width=True, hide_index=True)

st.caption(f"Atualizado em: {datetime.now().strftime('%d/%m/%Y %H:%M')}")

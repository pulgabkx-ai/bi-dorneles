import streamlit as st
import pandas as pd
import plotly.express as px
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta

# --- 1. CONFIGURAÇÃO E CONEXÃO ---
st.set_page_config(page_title="BI Dorneles Soluções", layout="wide", page_icon="📊")

@st.cache_resource
def conectar_google_sheets():
    escopos = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    try:
        if "gcp_service_account" in st.secrets:
            info = dict(st.secrets["gcp_service_account"])
            if "private_key" in info:
                info["private_key"] = info["private_key"].strip().strip('"').strip("'").replace("\\n", "\n")
            info["token_uri"] = "https://accounts.google.com/o/oauth2/token"
            creds = Credentials.from_service_account_info(info, scopes=escopos)
        else:
            creds = Credentials.from_service_account_file('credenciais-dorneles.json', scopes=escopos)
        client = gspread.authorize(creds)
        url = "https://docs.google.com/spreadsheets/d/18XXK_Wqz2Stb_dFDb5sfl-u9W0B5kHqioc3Ar1xK2Is/edit"
        return client.open_by_url(url).sheet1
    except Exception as e:
        st.error(f"Erro de Conexão: {e}"); st.stop()

@st.cache_data(ttl=60)
def buscar_e_limpar_dados():
    aba = conectar_google_sheets()
    df = pd.DataFrame(aba.get_all_records())
    if df.empty: return df
    df.columns = [str(col).strip() for col in df.columns]
    for col in ['Valor Estimado', 'Valor Final', 'Custo Frete']:
        df[col] = pd.to_numeric(df[col].astype(str).str.replace(r'[R\$\s\.]', '', regex=True).str.replace(',', '.'), errors='coerce').fillna(0)
    df['Data de Entrada'] = pd.to_datetime(df['Data de Entrada'], dayfirst=True, errors='coerce')
    df = df.dropna(subset=['Data de Entrada'])
    df['Dias em Processo'] = (datetime.now() - df['Data de Entrada']).dt.days.fillna(0).astype(int)
    return df

# --- 2. FILTROS ---
df_base = buscar_e_limpar_dados()
if df_base.empty: st.stop()

st.sidebar.header("🎯 Filtros")
d_min, d_max = df_base['Data de Entrada'].min().to_pydatetime(), df_base['Data de Entrada'].max().to_pydatetime()
periodo = st.sidebar.date_input("Período Selecionado", value=(d_min, d_max))

# Checkbox para ativar o comparativo sem poluir o dash
exibir_comparativo = st.sidebar.checkbox("Ativar Comparativo de Datas", value=False)

sel_op = st.sidebar.multiselect("Operadores", options=sorted(df_base['Operador'].unique()), default=sorted(df_base['Operador'].unique()))
sel_st = st.sidebar.multiselect("Status", options=sorted(df_base['Status'].unique()), default=sorted(df_base['Status'].unique()))

# --- 3. LÓGICA DE DADOS ---
df_f = df_base.copy()
if isinstance(periodo, (list, tuple)) and len(periodo) == 2:
    data_ini, data_fim = periodo[0], periodo[1]
    df_f = df_base[(df_base['Data de Entrada'].dt.date >= data_ini) & (df_base['Data de Entrada'].dt.date <= data_fim)]
    
    # Cálculo do Período Anterior (apenas se o checkbox estiver ativo)
    if exibir_comparativo:
        diff = (data_fim - data_ini).days + 1
        ini_ant, fim_ant = data_ini - timedelta(days=diff), data_ini - timedelta(days=1)
        df_ant = df_base[(df_base['Data de Entrada'].dt.date >= ini_ant) & (df_base['Data de Entrada'].dt.date <= fim_ant)]

df_f = df_f[(df_f['Operador'].isin(sel_op)) & (df_f['Status'].isin(sel_st))]

# --- 4. DASHBOARD ---
st.title("📊 BI Dorneles Soluções")

# SEÇÃO DE COMPARATIVO (ADICIONAL)
if exibir_comparativo and not df_ant.empty:
    with st.expander("🔄 Análise Comparativa (Período Atual vs. Anterior)", expanded=True):
        c1, c2, c3 = st.columns(3)
        
        def calc_delta(atual, anterior):
            return ((atual - anterior) / anterior * 100) if anterior > 0 else 0

        v_orc_at = df_f['Valor Estimado'].sum()
        v_orc_ant = df_ant['Valor Estimado'].sum()
        c1.metric("Evolução Orçados", f"R$ {v_orc_at:,.2f}", f"{calc_delta(v_orc_at, v_orc_ant):.1f}%")

        v_real_at = df_f[df_f['Status'].str.lower() == 'fechado']['Valor Final'].sum()
        v_real_ant = df_ant[df_ant['Status'].str.lower() == 'fechado']['Valor Final'].sum()
        c2.metric("Evolução Fechados", f"R$ {v_real_at:,.2f}", f"{calc_delta(v_real_at, v_real_ant):.1f}%")
        
        c3.metric("Qtd Leads", len(df_f), f"{len(df_f) - len(df_ant)} leads")
        st.caption(f"Comparado com: {ini_ant.strftime('%d/%m')} a {fim_ant.strftime('%d/%m')}")

# DASHBOARD ORIGINAL (MANTIDO)
tab_vendas, tab_perf = st.tabs(["🚀 Geral", "📈 Performance"])

with tab_vendas:
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Orçado", f"R$ {df_f['Valor Estimado'].sum():,.2f}")
    col2.metric("Total Fechado", f"R$ {df_f[df_f['Status'].str.lower() == 'fechado']['Valor Final'].sum():,.2f}")
    col3.metric("Leads Ativos", len(df_f))
    
    st.divider()
    st.plotly_chart(px.funnel(df_f.groupby('Status')['Valor Estimado'].sum().reset_index().sort_values('Valor Estimado', ascending=False), 
                              y='Status', x='Valor Estimado', title="Funil de Vendas"), use_container_width=True)
    st.dataframe(df_f, use_container_width=True, hide_index=True)

with tab_perf:
    # Gráfico de evolução mensal com correção 'ME'
    df_t = df_f.set_index('Data de Entrada').resample('ME').agg({'Valor Estimado': 'sum', 'Valor Final': 'sum'}).reset_index()
    if not df_t.empty:
        st.plotly_chart(px.line(df_t, x='Data de Entrada', y=['Valor Estimado', 'Valor Final'], markers=True, title="Tendência Mensal"), use_container_width=True)

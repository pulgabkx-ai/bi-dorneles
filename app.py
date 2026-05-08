import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta

# --- 1. CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="BI Dorneles Soluções", layout="wide", page_icon="📊")

# --- 2. FUNÇÕES DE DADOS (Otimizadas) ---
@st.cache_resource
def conectar_google_sheets():
    escopos = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    if "gcp_service_account" in st.secrets:
        info_chaves = dict(st.secrets["gcp_service_account"])
        if "private_key" in info_chaves:
            pk = info_chaves["private_key"].strip().strip('"').strip("'")
            info_chaves["private_key"] = pk.replace("\\n", "\n")
        info_chaves["token_uri"] = "https://accounts.google.com/o/oauth2/token"
        creds = Credentials.from_service_account_info(info_chaves, scopes=escopos)
    else:
        creds = Credentials.from_service_account_file('credenciais-dorneles.json', scopes=escopos)
    
    client = gspread.authorize(creds)
    url_da_planilha = "https://docs.google.com/spreadsheets/d/18XXK_Wqz2Stb_dFDb5sfl-u9W0B5kHqioc3Ar1xK2Is/edit"
    return client.open_by_url(url_da_planilha).sheet1

@st.cache_data(ttl=60)
def buscar_e_limpar_dados():
    aba = conectar_google_sheets()
    df = pd.DataFrame(aba.get_all_records())
    if df.empty: return df

    df.columns = [str(col).strip() for col in df.columns]
    colunas_obrigatorias = ['Status', 'Valor Estimado', 'Valor Final', 'Custo Frete', 
                            'Operador', 'Data de Entrada', 'Cidade', 'Motivo da Perda']
    for col in colunas_obrigatorias:
        if col not in df.columns:
            df[col] = 0 if 'Valor' in col or 'Custo' in col else ""

    colunas_moeda = ['Valor Estimado', 'Valor Final', 'Custo Frete']
    for col in colunas_moeda:
        df[col] = pd.to_numeric(
            df[col].astype(str).str.replace(r'[R\$\s\.]', '', regex=True).str.replace(',', '.'), 
            errors='coerce'
        ).fillna(0)
    
    df['Data de Entrada'] = pd.to_datetime(df['Data de Entrada'], dayfirst=True, errors='coerce')
    df = df.dropna(subset=['Data de Entrada'])
    df['Dias em Processo'] = (datetime.now() - df['Data de Entrada']).dt.days.fillna(0).astype(int)
    return df

# --- 3. INICIALIZAÇÃO ---
try:
    df_base = buscar_e_limpar_dados()
    if df_base.empty:
        st.warning("Nenhum dado encontrado.")
        st.stop()
except Exception as e:
    st.error(f"Erro: {e}"); st.stop()

# --- 4. BARRA LATERAL (Filtros + Metas) ---
st.sidebar.header("🎯 Painel de Controle")
meta_input = st.sidebar.number_input("Definir Meta Mensal (R$)", value=50000, step=5000)

data_min, data_max = df_base['Data de Entrada'].min().to_pydatetime(), df_base['Data de Entrada'].max().to_pydatetime()
periodo = st.sidebar.date_input("Período de Entrada", value=(data_min, data_max))

def criar_filtro(titulo, coluna):
    opcoes = sorted(df_base[coluna].astype(str).unique().tolist())
    return st.sidebar.multiselect(titulo, options=opcoes, default=opcoes)

sel_operadores = criar_filtro("Operadores", "Operador")
sel_status = criar_filtro("Status Atual", "Status")
sel_cidades = criar_filtro("Cidades", "Cidade")

# --- 5. LÓGICA DE FILTRAGEM ---
df_f = df_base.copy()
if isinstance(periodo, tuple) and len(periodo) == 2:
    df_f = df_f[(df_f['Data de Entrada'].dt.date >= periodo[0]) & (df_f['Data de Entrada'].dt.date <= periodo[1])]

df_f = df_f[
    (df_f['Operador'].astype(str).isin(sel_operadores)) & 
    (df_f['Status'].astype(str).isin(sel_status)) & 
    (df_f['Cidade'].astype(str).isin(sel_cidades))
]

# --- 6. FUNÇÃO DO FATOR WOW (Sankey e Gauge) ---
def renderizar_wow_metrics(df_filtrado, meta):
    st.markdown("### ⚡ Radar Estratégico")
    cw1, cw2 = st.columns([1, 2])
    
    with cw1:
        # Velocímetro de Meta
        total_fat = df_filtrado[df_filtrado['Status'].astype(str).str.lower() == 'fechado']['Valor Final'].sum()
        fig_gauge = go.Figure(go.Indicator(
            mode = "gauge+number+delta",
            value = total_fat,
            delta = {'reference': meta},
            title = {'text': "Progresso da Meta", 'font': {'size': 18}},
            gauge = {
                'axis': {'range': [None, meta]},
                'bar': {'color': "#1C83E1"},
                'steps': [
                    {'range': [0, meta*0.5], 'color': "#f8d7da"},
                    {'range': [meta*0.8, meta], 'color': "#d1e7dd"}]}))
        fig_gauge.update_layout(height=280, margin=dict(l=20, r=20, t=40, b=20))
        st.plotly_chart(fig_gauge, use_container_width=True)

    with cw2:
        # Fluxo Sankey (Operador -> Status)
        df_sankey = df_filtrado.groupby(['Operador', 'Status'])['Valor Estimado'].sum().reset_index()
        all_nodes = list(pd.concat([df_sankey['Operador'], df_sankey['Status']]).unique())
        map_nodes = {name: i for i, name in enumerate(all_nodes)}
        
        fig_sankey = go.Figure(data=[go.Sankey(
            node = dict(pad=15, thickness=20, label=all_nodes, color="#1C83E1"),
            link = dict(
                source=df_sankey['Operador'].map(map_nodes),
                target=df_sankey['Status'].map(map_nodes),
                value=df_sankey['Valor Estimado'],
                color="rgba(28, 131, 225, 0.2)"
            ))])
        fig_sankey.update_layout(title_text="Fluxo de Valor: Operador → Status", height=280, margin=dict(l=0, r=0, t=40, b=0))
        st.plotly_chart(fig_sankey, use_container_width=True)

# --- 7. INTERFACE PRINCIPAL ---
st.title("📊 BI Dorneles Soluções")
tab_sucesso, tab_perdas, tab_ads = st.tabs(["🚀 Visão Geral", "🔍 Análise de Perdas", "📱 Meta Ads"])

with tab_sucesso:
    # Métricas principais
    m1, m2, m3, m4 = st.columns(4)
    total_est = df_f['Valor Estimado'].sum()
    total_fat = df_f[df_f['Status'].astype(str).str.lower() == 'fechado']['Valor Final'].sum()
    
    m1.metric("Orçamentos Totais", f"R$ {total_est:,.2f}")
    m2.metric("Faturamento Real", f"R$ {total_fat:,.2f}", delta=f"{(total_fat/total_est*100 if total_est > 0 else 0):.1f}% conv.")
    m3.metric("Investimento Frete", f"R$ {df_f['Custo Frete'].sum():,.2f}")
    m4.metric("Ticket Médio", f"R$ {(total_fat/len(df_f[df_f['Status']=='Fechado']) if not df_f[df_f['Status']=='Fechado'].empty else 0):,.2f}")

    # Inserção do Fator WOW logo abaixo das métricas
    renderizar_wow_metrics(df_f, meta_input)

    st.markdown("---")
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("🎯 Funil de Vendas")
        df_funnel = df_f.groupby('Status')['Valor Estimado'].sum().reset_index().sort_values('Valor Estimado', ascending=False)
        fig_funnel = px.funnel(df_funnel, y='Status', x='Valor Estimado', color='Status', color_discrete_map={"Perdido": "#FF4B4B", "Fechado": "#2E8B57"})
        st.plotly_chart(fig_funnel, use_container_width=True)

    with col2:
        st.subheader("🚀 Faturamento por Operador")
        df_op = df_f.groupby('Operador')['Valor Final'].sum().reset_index()
        st.plotly_chart(px.bar(df_op, x='Operador', y='Valor Final', color_discrete_sequence=['#2E8B57']), use_container_width=True)

    st.subheader("📋 Detalhes dos Leads")
    st.dataframe(df_f, use_container_width=True, hide_index=True)

with tab_perdas:
    df_p = df_f[df_f['Status'].astype(str).str.lower() == 'perdido']
    if df_p.empty:
        st.success("Nenhuma perda registrada!")
    else:
        st.header("❌ Análise de Desistências")
        cp1, cp2 = st.columns(2)
        with cp1:
            motivos = df_p[df_p['Motivo da Perda'].astype(str).str.strip() != '']
            if not motivos.empty:
                st.plotly_chart(px.pie(motivos, names='Motivo da Perda', values='Valor Estimado', hole=0.4), use_container_width=True)
        with cp2:
            df_p_op = df_p.groupby('Operador')['Valor Estimado'].sum().reset_index()
            st.plotly_chart(px.bar(df_p_op, x='Operador', y='Valor Estimado', color_discrete_sequence=['#8B0000']), use_container_width=True)
        st.dataframe(df_p[['Data de Entrada', 'Cliente', 'Motivo da Perda', 'Valor Estimado', 'Operador']], use_container_width=True, hide_index=True)

with tab_ads:
    st.info("🚧 Módulo Meta Ads em desenvolvimento.")

st.caption(f"Última atualização: {datetime.now().strftime('%d/%m/%Y %H:%M')} | BI Dorneles Soluções")

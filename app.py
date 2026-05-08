import streamlit as st
import pandas as pd
import plotly.express as px
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

# --- 1. CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="BI Dorneles Soluções", layout="wide", page_icon="📊")

# --- 2. FUNÇÕES DE DADOS COM SEGURANÇA E CACHE ---
@st.cache_resource
def conectar_google_sheets():
    """Conecta ao Sheets priorizando Secrets (Nuvem) com fallback para JSON (Local)"""
    escopos = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    
    try:
        if "gcp_service_account" in st.secrets:
            info = dict(st.secrets["gcp_service_account"])
            # Limpeza da chave privada para evitar erro de assinatura JWT
            if "private_key" in info:
                info["private_key"] = info["private_key"].strip().strip('"').strip("'").replace("\\n", "\n")
            info["token_uri"] = "https://accounts.google.com/o/oauth2/token"
            creds = Credentials.from_service_account_info(info, scopes=escopos)
        else:
            # Fallback para credenciais locais durante desenvolvimento
            creds = Credentials.from_service_account_file('credenciais-dorneles.json', scopes=escopos)
        
        client = gspread.authorize(creds)
        url_planilha = "https://docs.google.com/spreadsheets/d/18XXK_Wqz2Stb_dFDb5sfl-u9W0B5kHqioc3Ar1xK2Is/edit"
        return client.open_by_url(url_planilha).sheet1
    except Exception as e:
        st.error(f"Erro Crítico de Conexão: {e}")
        st.stop()

@st.cache_data(ttl=60)
def buscar_e_limpar_dados():
    """Busca, limpa e protege os dados contra colunas ausentes ou formatadas errado"""
    aba = conectar_google_sheets()
    df = pd.DataFrame(aba.get_all_records())
    
    if df.empty:
        return df

    # Padronização de colunas (remove espaços e evita KeyError)
    df.columns = [str(col).strip() for col in df.columns]
    
    # Garantia de colunas mínimas para o BI não quebrar
    colunas_fatais = ['Status', 'Valor Estimado', 'Valor Final', 'Custo Frete', 'Operador', 'Data de Entrada', 'Cidade', 'Motivo da Perda']
    for col in colunas_fatais:
        if col not in df.columns:
            df[col] = 0 if 'Valor' in col or 'Custo' in col else ""

    # Conversão de Moeda (Trata R$, pontos e vírgulas)
    for col in ['Valor Estimado', 'Valor Final', 'Custo Frete']:
        df[col] = pd.to_numeric(
            df[col].astype(str).str.replace(r'[R\$\s\.]', '', regex=True).str.replace(',', '.'), 
            errors='coerce'
        ).fillna(0)
    
    # Tratamento de Datas e Dias em Aberto
    df['Data de Entrada'] = pd.to_datetime(df['Data de Entrada'], dayfirst=True, errors='coerce')
    df = df.dropna(subset=['Data de Entrada'])
    df['Dias em Processo'] = (datetime.now() - df['Data de Entrada']).dt.days.fillna(0).astype(int)
    
    return df

# --- 3. PROCESSAMENTO INICIAL ---
try:
    df_base = buscar_e_limpar_dados()
except Exception as e:
    st.error(f"Erro ao processar dados da planilha: {e}")
    st.stop()

# --- 4. BARRA LATERAL (FILTROS) ---
st.sidebar.header("🎯 Painel de Controle")

# Filtro de Data
data_min = df_base['Data de Entrada'].min().to_pydatetime()
data_max = df_base['Data de Entrada'].max().to_pydatetime()
periodo = st.sidebar.date_input("Período de Entrada", value=(data_min, data_max))

# Filtros Multiselect
def preparar_filtro(titulo, coluna):
    opcoes = sorted(df_base[coluna].astype(str).unique().tolist())
    return st.sidebar.multiselect(titulo, options=opcoes, default=opcoes)

sel_op = preparar_filtro("Operadores", "Operador")
sel_st = preparar_filtro("Status Atual", "Status")
sel_cid = preparar_filtro("Cidades", "Cidade")

# Aplicação da Filtragem
df_f = df_base.copy()
if isinstance(periodo, tuple) and len(periodo) == 2:
    df_f = df_f[(df_f['Data de Entrada'].dt.date >= periodo[0]) & (df_f['Data de Entrada'].dt.date <= periodo[1])]

df_f = df_f[
    (df_f['Operador'].astype(str).isin(sel_op)) & 
    (df_f['Status'].astype(str).isin(sel_st)) & 
    (df_f['Cidade'].astype(str).isin(sel_cid))
]

# --- 5. ALERTAS DE INTELIGÊNCIA (LEADS PARADOS) ---
leads_atencao = df_f[(df_f['Status'].str.contains('Aberto|Orçamento', case=False, na=False)) & (df_f['Dias em Processo'] > 5)]
if not leads_atencao.empty:
    with st.expander(f"⚠️ ATENÇÃO: {len(leads_atencao)} leads sem fechamento há mais de 5 dias", expanded=True):
        st.dataframe(
            leads_atencao[['Cliente', 'Operador', 'Dias em Processo', 'Valor Estimado']].sort_values('Dias em Processo', ascending=False),
            use_container_width=True, hide_index=True
        )

# --- 6. DASHBOARD (ESTRUTURA DE ABAS) ---
st.title("📊 BI Dorneles Soluções")
tab_vendas, tab_performance, tab_perdas = st.tabs(["🚀 Visão Geral", "📈 Performance & Tendências", "🔍 Análise de Perdas"])

with tab_vendas:
    # Métricas de Topo
    c1, c2, c3, c4 = st.columns(4)
    total_orcado = df_f['Valor Estimado'].sum()
    df_fechado = df_f[df_f['Status'].astype(str).str.lower() == 'fechado']
    total_recebido = df_fechado['Valor Final'].sum()
    
    c1.metric("Orçado Total", f"R$ {total_orcado:,.2f}")
    c2.metric("Faturamento Real", f"R$ {total_recebido:,.2f}", 
              delta=f"{(total_recebido/total_orcado*100 if total_orcado > 0 else 0):.1f}% de Conversão")
    c3.metric("Custo Frete", f"R$ {df_f['Custo Frete'].sum():,.2f}")
    c4.metric("Ticket Médio", f"R$ {(total_recebido/len(df_fechado) if len(df_fechado) > 0 else 0):,.2f}")

    st.divider()

    col_g1, col_g2 = st.columns(2)
    with col_g1:
        st.subheader("🎯 Funil de Vendas")
        df_funnel = df_f.groupby('Status')['Valor Estimado'].sum().reset_index().sort_values('Valor Estimado', ascending=False)
        fig_f = px.funnel(df_funnel, y='Status', x='Valor Estimado', color='Status',
                          color_discrete_map={"Perdido": "#FF4B4B", "Fechado": "#2E8B57", "Em Aberto": "#1C83E1"})
        st.plotly_chart(fig_f, use_container_width=True)

    with col_g2:
        st.subheader("📋 Últimos Leads")
        st.dataframe(df_f[['Data de Entrada', 'Cliente', 'Status', 'Operador', 'Valor Final']].tail(10), use_container_width=True, hide_index=True)

with tab_performance:
    st.subheader("📈 Evolução Mensal (Demanda vs Fechamento)")
    df_t = df_f.set_index('Data de Entrada').resample('M').agg({'Valor Estimado': 'sum', 'Valor Final': 'sum'}).reset_index()
    fig_t = px.line(df_t, x='Data de Entrada', y=['Valor Estimado', 'Valor Final'], markers=True,
                    color_discrete_map={'Valor Estimado': '#1C83E1', 'Valor Final': '#2E8B57'})
    st.plotly_chart(fig_t, use_container_width=True)

    st.divider()

    st.subheader("🥇 Eficiência por Operador")
    df_rank = df_f.groupby('Operador').agg({'Valor Estimado': 'sum', 'Valor Final': 'sum'}).reset_index()
    df_rank['Conversão %'] = (df_rank['Valor Final'] / df_rank['Valor Estimado'] * 100).fillna(0)
    
    st.plotly_chart(px.bar(df_rank, x='Operador', y='Conversão %', text_auto='.1f', color='Conversão %', color_continuous_scale='Greens'), use_container_width=True)

with tab_perdas:
    df_p = df_f[df_f['Status'].astype(str).str.lower() == 'perdido']
    if df_p.empty:
        st.success("Nenhuma perda registrada!")
    else:
        st.subheader("❌ Motivos de Desistência")
        motivos = df_p[df_p['Motivo da Perda'].astype(str).str.strip() != ""]
        if not motivos.empty:
            st.plotly_chart(px.pie(motivos, names='Motivo da Perda', values='Valor Estimado', hole=0.4), use_container_width=True)
        st.dataframe(df_p[['Cliente', 'Motivo da Perda', 'Valor Estimado', 'Operador']], use_container_width=True)

st.caption(f"Dorneles Soluções | Atualizado em {datetime.now().strftime('%d/%m/%Y %H:%M')}")

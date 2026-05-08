import streamlit as st
import pandas as pd
import plotly.express as px
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

# --- 1. CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="BI Dorneles Soluções", layout="wide", page_icon="📊")

# --- 2. CONEXÃO ESTÁVEL (DORNELES SOLUÇÕES) ---
@st.cache_resource
def conectar_google_sheets():
    """Conecta ao Sheets via Secrets (Nuvem) ou JSON (Local) com limpeza de JWT"""
    escopos = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    try:
        if "gcp_service_account" in st.secrets:
            info = dict(st.secrets["gcp_service_account"])
            if "private_key" in info:
                # Limpeza profunda para evitar Invalid JWT Signature
                info["private_key"] = info["private_key"].strip().strip('"').strip("'").replace("\\n", "\n")
            info["token_uri"] = "https://accounts.google.com/o/oauth2/token"
            creds = Credentials.from_service_account_info(info, scopes=escopos)
        else:
            creds = Credentials.from_service_account_file('credenciais-dorneles.json', scopes=escopos)
        
        client = gspread.authorize(creds)
        # URL fixa da planilha Dorneles Soluções
        url = "https://docs.google.com/spreadsheets/d/18XXK_Wqz2Stb_dFDb5sfl-u9W0B5kHqioc3Ar1xK2Is/edit"
        return client.open_by_url(url).sheet1
    except Exception as e:
        st.error(f"Erro de Conexão: {e}")
        st.stop()

# --- 3. LIMPEZA E PROTEÇÃO DE DADOS (ANTI-VALUEERROR) ---
@st.cache_data(ttl=60)
def buscar_e_limpar_dados():
    aba = conectar_google_sheets()
    df = pd.DataFrame(aba.get_all_records())
    
    if df.empty:
        return df

    # Padronização de colunas
    df.columns = [str(col).strip() for col in df.columns]
    
    # Colunas essenciais
    colunas_fatais = ['Status', 'Valor Estimado', 'Valor Final', 'Custo Frete', 'Operador', 'Data de Entrada', 'Cidade', 'Motivo da Perda']
    for col in colunas_fatais:
        if col not in df.columns:
            df[col] = 0 if 'Valor' in col or 'Custo' in col else ""

    # Conversão de Moeda
    for col in ['Valor Estimado', 'Valor Final', 'Custo Frete']:
        df[col] = pd.to_numeric(df[col].astype(str).str.replace(r'[R\$\s\.]', '', regex=True).str.replace(',', '.'), errors='coerce').fillna(0)
    
    # Tratamento de Datas (Blindagem contra ValueError)
    df['Data de Entrada'] = pd.to_datetime(df['Data de Entrada'], dayfirst=True, errors='coerce')
    df = df.dropna(subset=['Data de Entrada']) # Remove datas inválidas que quebram filtros
    
    # Cálculo de tempo em aberto
    df['Dias em Processo'] = (datetime.now() - df['Data de Entrada']).dt.days.fillna(0).astype(int)
    
    return df

# --- 4. FILTROS E LÓGICA ---
try:
    df_base = buscar_e_limpar_dados()
    if df_base.empty:
        st.info("Aguardando preenchimento da planilha...")
        st.stop()

    st.sidebar.header("🎯 Painel de Controle")
    
    # Filtro de Data Protegido
    try:
        d_min, d_max = df_base['Data de Entrada'].min().to_pydatetime(), df_base['Data de Entrada'].max().to_pydatetime()
        periodo = st.sidebar.date_input("Período de Entrada", value=(d_min, d_max))
    except:
        st.sidebar.error("Verifique os formatos de data na planilha.")
        st.stop()

    # Filtros de Texto
    def multiselect_safe(titulo, coluna):
        opcoes = sorted(df_base[coluna].astype(str).unique().tolist())
        return st.sidebar.multiselect(titulo, options=opcoes, default=opcoes)

    sel_op = multiselect_safe("Operadores", "Operador")
    sel_st = multiselect_safe("Status Atual", "Status")
    sel_cid = multiselect_safe("Cidades", "Cidade")

    # Aplicação da Filtragem (Proteção contra seleção incompleta de data)
    df_f = df_base.copy()
    if isinstance(periodo, (list, tuple)) and len(periodo) == 2:
        df_f = df_f[(df_f['Data de Entrada'].dt.date >= periodo[0]) & (df_f['Data de Entrada'].dt.date <= periodo[1])]

    df_f = df_f[
        (df_f['Operador'].astype(str).isin(sel_op)) & 
        (df_f['Status'].astype(str).isin(sel_st)) & 
        (df_f['Cidade'].astype(str).isin(sel_cid))
    ]

    # --- 5. INTERFACE (ESTRUTURA DE ABAS) ---
    st.title("📊 BI Dorneles Soluções")

    # FEATURE: ALERTA DE LEADS PARADOS
    leads_alerta = df_f[(df_f['Status'].str.contains('Aberto|Orçamento', case=False, na=False)) & (df_f['Dias em Processo'] > 5)]
    if not leads_alerta.empty:
        with st.expander(f"⚠️ ATENÇÃO: {len(leads_alerta)} leads parados há mais de 5 dias", expanded=True):
            st.dataframe(leads_alerta[['Cliente', 'Operador', 'Dias em Processo', 'Valor Estimado']].sort_values('Dias em Processo', ascending=False), use_container_width=True, hide_index=True)

    tab_vendas, tab_performance, tab_perdas = st.tabs(["🚀 Visão Geral", "📈 Performance & Tendências", "🔍 Análise de Perdas"])

    with tab_vendas:
        # Métricas
        c1, c2, c3, c4 = st.columns(4)
        total_orcado = df_f['Valor Estimado'].sum()
        df_fechado = df_f[df_f['Status'].astype(str).str.lower() == 'fechado']
        total_real = df_fechado['Valor Final'].sum()
        
        c1.metric("Orçado Total", f"R$ {total_orcado:,.2f}")
        c2.metric("Faturamento Real", f"R$ {total_real:,.2f}", delta=f"{(total_real/total_orcado*100 if total_orcado > 0 else 0):.1f}% Conv.")
        c3.metric("Custo Frete", f"R$ {df_f['Custo Frete'].sum():,.2f}")
        c4.metric("Ticket Médio", f"R$ {(total_real/len(df_fechado) if len(df_fechado) > 0 else 0):,.2f}")

        st.divider()

        # Funil Protegido
        if not df_f.empty:
            st.subheader("🎯 Funil de Vendas")
            df_fun = df_f.groupby('Status')['Valor Estimado'].sum().reset_index().sort_values('Valor Estimado', ascending=False)
            fig_fun = px.funnel(df_fun, y='Status', x='Valor Estimado', color='Status', 
                                color_discrete_map={"Perdido": "#FF4B4B", "Fechado": "#2E8B57", "Em Aberto": "#1C83E1"})
            st.plotly_chart(fig_fun, use_container_width=True)

    with tab_performance:
        st.subheader("📈 Evolução Mensal (Orçado vs Fechado)")
        # Agrupamento temporal com proteção contra períodos vazios
        df_t = df_f.set_index('Data de Entrada').resample('M').agg({'Valor Estimado': 'sum', 'Valor Final': 'sum'}).reset_index()
        if not df_t.empty:
            fig_t = px.line(df_t, x='Data de Entrada', y=['Valor Estimado', 'Valor Final'], markers=True,
                            color_discrete_map={'Valor Estimado': '#1C83E1', 'Valor Final': '#2E8B57'})
            st.plotly_chart(fig_t, use_container_width=True)

        st.divider()
        
        st.subheader("🥇 Ranking de Eficiência (Taxa de Conversão)")
        df_rank = df_f.groupby('Operador').agg({'Valor Estimado': 'sum', 'Valor Final': 'sum'}).reset_index()
        df_rank['Conversão %'] = (df_rank['Valor Final'] / df_rank['Valor Estimado'] * 100).fillna(0)
        if not df_rank.empty:
            st.plotly_chart(px.bar(df_rank, x='Operador', y='Conversão %', text_auto='.1f', color='Conversão %', color_continuous_scale='Greens'), use_container_width=True)

    with tab_perdas:
        df_p = df_f[df_f['Status'].astype(str).str.lower() == 'perdido']
        if df_p.empty:
            st.success("Nenhuma perda registrada no período!")
        else:
            st.subheader("❌ Motivos de Desistência")
            motivos = df_p[df_p['Motivo da Perda'].astype(str).str.strip() != ""]
            if not motivos.empty:
                st.plotly_chart(px.pie(motivos, names='Motivo da Perda', values='Valor Estimado', hole=0.4), use_container_width=True)
            st.dataframe(df_p[['Cliente', 'Motivo da Perda', 'Valor Estimado', 'Operador']], use_container_width=True, hide_index=True)

except Exception as e:
    st.error(f"Erro inesperado: {e}")

st.caption(f"Dorneles Soluções | BI Atualizado em {datetime.now().strftime('%d/%m/%Y %H:%M')}")

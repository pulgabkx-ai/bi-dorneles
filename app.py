import streamlit as st
import pandas as pd
import plotly.express as px
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta

# --- 1. CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="BI Dorneles Soluções", layout="wide", page_icon="📊")

# --- 2. CONEXÃO SEGURA E ESTÁVEL ---
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
        st.error(f"Erro de Conexão: {e}")
        st.stop()

# --- 3. PROCESSAMENTO DE DADOS (ANTI-ERRO) ---
@st.cache_data(ttl=60)
def buscar_e_limpar_dados():
    aba = conectar_google_sheets()
    df = pd.DataFrame(aba.get_all_records())
    
    if df.empty:
        return df

    df.columns = [str(col).strip() for col in df.columns]
    
    colunas_fatais = ['Status', 'Valor Estimado', 'Valor Final', 'Custo Frete', 'Operador', 'Data de Entrada', 'Cidade', 'Motivo da Perda']
    for col in colunas_fatais:
        if col not in df.columns:
            df[col] = 0 if 'Valor' in col or 'Custo' in col else ""

    for col in ['Valor Estimado', 'Valor Final', 'Custo Frete']:
        df[col] = pd.to_numeric(df[col].astype(str).str.replace(r'[R\$\s\.]', '', regex=True).str.replace(',', '.'), errors='coerce').fillna(0)
    
    df['Data de Entrada'] = pd.to_datetime(df['Data de Entrada'], dayfirst=True, errors='coerce')
    df = df.dropna(subset=['Data de Entrada'])
    
    df['Dias em Processo'] = (datetime.now() - df['Data de Entrada']).dt.days.fillna(0).astype(int)
    return df

# --- 4. EXECUÇÃO E LÓGICA DE FILTROS ---
try:
    df_base = buscar_e_limpar_dados()
    if df_base.empty:
        st.info("Aguardando dados na planilha...")
        st.stop()

    st.sidebar.header("🎯 Painel de Controle")
    
    # Filtro de Data
    d_min, d_max = df_base['Data de Entrada'].min().to_pydatetime(), df_base['Data de Entrada'].max().to_pydatetime()
    periodo = st.sidebar.date_input("Período de Entrada", value=(d_min, d_max))

    # Seletores dinâmicos
    def filter_box(label, col):
        opt = sorted(df_base[col].astype(str).unique().tolist())
        return st.sidebar.multiselect(label, options=opt, default=opt)

    sel_op = filter_box("Operadores", "Operador")
    sel_st = filter_box("Status Atual", "Status")
    sel_cid = filter_box("Cidades", "Cidade")

    # LÓGICA DE COMPARAÇÃO DE PERÍODOS
    df_f = df_base.copy()
    delta_orcado = 0
    delta_realizado = 0
    msg_periodo = ""

    if isinstance(periodo, (list, tuple)) and len(periodo) == 2:
        data_inicio, data_fim = periodo[0], periodo[1]
        diff_dias = (data_fim - data_inicio).days + 1
        
        # Filtro Período Atual
        df_f = df_base[(df_base['Data de Entrada'].dt.date >= data_inicio) & (df_base['Data de Entrada'].dt.date <= data_fim)]
        
        # Filtro Período Anterior
        inicio_ant = data_inicio - timedelta(days=diff_dias)
        fim_ant = data_inicio - timedelta(days=1)
        df_ant = df_base[(df_base['Data de Entrada'].dt.date >= inicio_ant) & (df_base['Data de Entrada'].dt.date <= fim_ant)]
        
        msg_periodo = f"Comparando com: {inicio_ant.strftime('%d/%m')} a {fim_ant.strftime('%d/%m')}"
        
        # Cálculos de Delta
        if not df_ant.empty:
            v_orc_atual = df_f['Valor Estimado'].sum()
            v_orc_ant = df_ant['Valor Estimado'].sum()
            v_real_atual = df_f[df_f['Status'].str.lower() == 'fechado']['Valor Final'].sum()
            v_real_ant = df_ant[df_ant['Status'].str.lower() == 'fechado']['Valor Final'].sum()
            
            delta_orcado = ((v_orc_atual - v_orc_ant) / v_orc_ant * 100) if v_orc_ant > 0 else 0
            delta_realizado = ((v_real_atual - v_real_ant) / v_real_ant * 100) if v_real_ant > 0 else 0

    # Aplicação dos filtros de texto
    df_f = df_f[
        (df_f['Operador'].astype(str).isin(sel_op)) & 
        (df_f['Status'].astype(str).isin(sel_st)) & 
        (df_f['Cidade'].astype(str).isin(sel_cid))
    ]

    # --- 5. INTERFACE DASHBOARD ---
    st.title("📊 BI Dorneles Soluções")

    # Alerta de Leads Parados
    leads_parados = df_f[(df_f['Status'].str.contains('Aberto|Orçamento', case=False, na=False)) & (df_f['Dias em Processo'] > 5)]
    if not leads_parados.empty:
        with st.expander(f"⚠️ ATENÇÃO: {len(leads_parados)} leads parados há mais de 5 dias", expanded=True):
            st.dataframe(leads_parados[['Cliente', 'Operador', 'Dias em Processo', 'Valor Estimado']], use_container_width=True, hide_index=True)

    tab1, tab2, tab3 = st.tabs(["🚀 Visão Geral", "📈 Performance", "🔍 Perdas"])

    with tab1:
        st.caption(msg_periodo)
        m1, m2, m3, m4 = st.columns(4)
        
        v_orc = df_f['Valor Estimado'].sum()
        df_fechados = df_f[df_f['Status'].str.lower() == 'fechado']
        v_real = df_fechados['Valor Final'].sum()
        
        m1.metric("Orçado Total", f"R$ {v_orc:,.2f}", delta=f"{delta_orcado:.1f}% vs. ant.")
        m2.metric("Faturamento Real", f"R$ {v_real:,.2f}", delta=f"{delta_realizado:.1f}% vs. ant.")
        m3.metric("Ticket Médio", f"R$ {(v_real/len(df_fechados) if not df_fechados.empty else 0):,.2f}")
        m4.metric("Qtd Leads", len(df_f))

        st.divider()
        st.subheader("🎯 Funil de Vendas (Orçado)")
        df_fun = df_f.groupby('Status')['Valor Estimado'].sum().reset_index().sort_values('Valor Estimado', ascending=False)
        if not df_fun.empty:
            st.plotly_chart(px.funnel(df_fun, y='Status', x='Valor Estimado', color='Status'), use_container_width=True)

    with tab2:
        st.subheader("📈 Evolução Mensal")
        # Correção ME para Pandas 2.2+
        df_t = df_f.set_index('Data de Entrada').resample('ME').agg({'Valor Estimado': 'sum', 'Valor Final': 'sum'}).reset_index()
        if not df_t.empty:
            fig_t = px.line(df_t, x='Data de Entrada', y=['Valor Estimado', 'Valor Final'], markers=True)
            st.plotly_chart(fig_t, use_container_width=True)

        st.divider()
        st.subheader("🥇 Eficiência por Operador")
        df_rank = df_f.groupby('Operador').agg({'Valor Estimado': 'sum', 'Valor Final': 'sum'}).reset_index()
        df_rank['Conversão %'] = (df_rank['Valor Final'] / df_rank['Valor Estimado'] * 100).fillna(0)
        st.plotly_chart(px.bar(df_rank, x='Operador', y='Conversão %', text_auto='.1f', color='Conversão %', color_continuous_scale='Greens'), use_container_width=True)

    with tab3:
        df_p = df_f[df_f['Status'].str.lower() == 'perdido']
        if not df_p.empty:
            st.subheader("❌ Motivos de Perda")
            motivos = df_p[df_p['Motivo da Perda'].str.strip() != ""]
            if not motivos.empty:
                st.plotly_chart(px.pie(motivos, names='Motivo da Perda', values='Valor Estimado', hole=0.4), use_container_width=True)
            st.dataframe(df_p[['Cliente', 'Motivo da Perda', 'Valor Estimado', 'Operador']], use_container_width=True, hide_index=True)
        else:
            st.success("Nenhuma perda registrada no período selecionado.")

except Exception as e:
    st.error(f"Erro de processamento: {e}")

st.caption(f"Atualizado em: {datetime.now().strftime('%d/%m/%Y %H:%M')}")

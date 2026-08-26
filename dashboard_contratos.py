import streamlit as st
import pandas as pd
import requests
import sqlite3
from datetime import datetime, date, timedelta
import io

# ==============================================================================
# FUNÇÃO AUXILIAR DE TRATAMENTO DE DATAS (BLINDAGEM CONTRA VALORES NULOS)
# ==============================================================================
def converter_data_segura(valor):
    """Converte com segurança qualquer formato de data sem travar o app"""
    if not valor or pd.isna(valor):
        return None
    v_str = str(valor).strip().split(" ")[0].split("T")[0]
    if v_str.lower() in ["none", "nan", "null", ""]:
        return None
    for formato in ["%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d"]:
        try:
            return datetime.strptime(v_str, formato).date()
        except ValueError:
            pass
    return None

# ==============================================================================
# CONFIGURAÇÃO GERAL DA PÁGINA & CSS RESPONSIVO
# ==============================================================================
st.set_page_config(
    page_title="Ecossistema NLLC - Governança e Operação de Contratos",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Estilização visual (Fontes menores nos KPIs e caixas de alerta oficiais)
st.markdown("""
<style>
    [data-testid="stMetricValue"] {
        font-size: 1.2rem !important;
        font-weight: 700 !important;
        color: #1E3A8A !important;
    }
    [data-testid="stMetricLabel"] {
        font-size: 0.85rem !important;
        font-weight: 600 !important;
        color: #4B5563 !important;
    }
    [data-testid="metric-container"] {
        background-color: #F8FAFC;
        border: 1px solid #E2E8F0;
        padding: 10px 12px;
        border-radius: 8px;
    }
    .alerta-federal {
        background-color: #FEF2F2;
        border-left: 5px solid #EF4444;
        padding: 12px;
        border-radius: 4px;
        color: #991B1B;
        margin-bottom: 12px;
        font-size: 0.9rem;
    }
    .alerta-local {
        background-color: #F0FDF4;
        border-left: 5px solid #22C55E;
        padding: 10px;
        border-radius: 4px;
        color: #166534;
        margin-bottom: 10px;
        font-size: 0.85rem;
    }
</style>
""", unsafe_allow_html=True)

# Inicialização de variáveis de sessão
if "autenticado" not in st.session_state:
    st.session_state["autenticado"] = False
    st.session_state["perfil"] = None
    st.session_state["nome_usuario"] = ""

if "token_comprasnet" not in st.session_state:
    st.session_state["token_comprasnet"] = None
    st.session_state["operador_comprasnet"] = None

# ==============================================================================
# 1. TELA DE LOGIN DO DASHBOARD
# ==============================================================================
def render_tela_login():
    st.markdown("<br><br>", unsafe_allow_html=True)
    st.markdown("<h2 style='text-align: center;'>🔒 Central de Gestão e Governança NLLC</h2>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: gray;'>Acesso restrito a servidores autorizados da UASG.</p>", unsafe_allow_html=True)
    
    col_l1, col_l2, col_l3 = st.columns([1, 2, 1])
    with col_l2:
        with st.form("form_login"):
            usuario = st.text_input("Usuário / Login:")
            senha = st.text_input("Senha de Acesso:", type="password")
            btn_entrar = st.form_submit_button("🔓 Acessar Sistema", use_container_width=True)

            if btn_entrar:
                user_clean = usuario.strip().lower()
                usuarios_validos = st.secrets.get("usuarios", {
                    "gestor": {"senha": "123", "perfil": "editor", "nome": "Francisco (Gestor)"},
                    "diretoria": {"senha": "456", "perfil": "leitor", "nome": "Gabinete da Diretoria"}
                })

                if user_clean in usuarios_validos and str(senha) == str(usuarios_validos[user_clean]["senha"]):
                    st.session_state["autenticado"] = True
                    st.session_state["perfil"] = usuarios_validos[user_clean]["perfil"]
                    st.session_state["nome_usuario"] = usuarios_validos[user_clean]["nome"]
                    st.success("Autenticado com sucesso!")
                    st.rerun()
                else:
                    st.error("❌ Usuário ou senha incorretos. Verifique as credenciais.")

# ==============================================================================
# 2. PAINEL PRINCIPAL (APÓS LOGIN)
# ==============================================================================
def render_painel_principal():
    perfil_usuario = st.session_state["perfil"]
    nome_usuario = st.session_state["nome_usuario"]

    # Barra lateral
    st.sidebar.markdown(f"👤 Conectado: **{nome_usuario}**")
    if perfil_usuario == "editor":
        st.sidebar.success("🔑 Perfil: **Gestor (Edição Liberada)**")
    else:
        st.sidebar.info("👁️ Perfil: **Diretoria (Somente Leitura)**")

    if st.sidebar.button("🚪 Sair do Painel"):
        st.session_state["autenticado"] = False
        st.session_state["perfil"] = None
        st.session_state["nome_usuario"] = ""
        st.session_state["token_comprasnet"] = None
        st.rerun()

    # Banco SQLite Local
    DB_PATH = "nllc_governance.db"
    def init_db():
        with sqlite3.connect(DB_PATH) as conn:
            c = conn.cursor()
            c.execute("""
                CREATE TABLE IF NOT EXISTS nllc_contratos (
                    id_contrato TEXT PRIMARY KEY,
                    tipo_regime TEXT DEFAULT 'SERVICO_CONTINUO',
                    tem_dedicacao_exclusiva INTEGER DEFAULT 0,
                    data_base_reajuste TEXT,
                    valor_aditado_acumulado REAL DEFAULT 0.0,
                    publicado_pncp INTEGER DEFAULT 1,
                    data_publicacao_pncp TEXT,
                    tipo_garantia TEXT DEFAULT 'Não Exigida',
                    valor_garantia REAL DEFAULT 0.0,
                    vencimento_garantia TEXT,
                    clausula_retomada INTEGER DEFAULT 0,
                    conta_vinculada_ativa INTEGER DEFAULT 0,
                    saldo_conta_vinculada REAL DEFAULT 0.0,
                    status_gestao TEXT DEFAULT 'Vigente / Em Execução',
                    gestor_nome TEXT DEFAULT 'Não Atribuído',
                    fiscal_tecnico TEXT DEFAULT 'Não Atribuído',
                    fiscal_administrativo TEXT DEFAULT 'Não Atribuído',
                    anotacoes_gerais TEXT DEFAULT ''
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS nllc_matriz_riscos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    id_contrato TEXT,
                    evento_risco TEXT,
                    probabilidade TEXT,
                    impacto TEXT,
                    acao_mitigadora TEXT,
                    responsavel TEXT,
                    status_risco TEXT DEFAULT 'Monitorado'
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS nllc_ocorrencias_sancoes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    id_contrato TEXT,
                    tipo_evento TEXT,
                    data_registro TEXT,
                    descricao TEXT,
                    valor_glosa REAL DEFAULT 0.0,
                    status_processo TEXT DEFAULT 'Registrado'
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS nllc_medicoes_imr (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    id_contrato TEXT,
                    periodo_ref TEXT,
                    sla_percentual REAL,
                    valor_medido REAL,
                    valor_glosado REAL,
                    termo_provisorio_emitido INTEGER DEFAULT 0,
                    data_emissao_termo TEXT
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS nllc_regularidade_trabalhista (
                    id_contrato TEXT PRIMARY KEY,
                    cnd_federal_valida INTEGER DEFAULT 1,
                    cndt_valida INTEGER DEFAULT 1,
                    fgts_valido INTEGER DEFAULT 1,
                    folha_salarios_paga INTEGER DEFAULT 1,
                    trava_liquidacao INTEGER DEFAULT 0
                )
            """)
            conn.commit()

    init_db()

    def db_query(query, params=()):
        with sqlite3.connect(DB_PATH) as conn:
            return pd.read_sql(query, conn, params=params)

    def db_execute(query, params=()):
        with sqlite3.connect(DB_PATH) as conn:
            c = conn.cursor()
            c.execute(query, params)
            conn.commit()

    def converter_moeda(v):
        if not v or pd.isna(v): return 0.0
        try: return float(str(v).replace(".", "").replace(",", "."))
        except: return 0.0

    @st.cache_data(ttl=300)
    def fetch_comprasnet(uasg):
        url = f"https://contratos.comprasnet.gov.br/api/contrato/ug/{uasg}"
        try:
            resp = requests.get(url, headers={"Accept": "application/json", "User-Agent": "Mozilla/5.0"}, timeout=15)
            if resp.status_code == 200:
                dados = resp.json()
                lista = []
                hoje_dt = datetime.now().date()
                for d in dados:
                    forn = d.get("fornecedor", {}) or {}
                    fim_vig = d.get("vigencia_fim")
                    dias_rest = None
                    if fim_vig:
                        try:
                            dt_fim = datetime.strptime(fim_vig, "%Y-%m-%d").date()
                            dias_rest = (dt_fim - hoje_dt).days
                        except: pass
                    
                    lista.append({
                        "id": str(d.get("id")),
                        "numero": d.get("numero", "N/A"),
                        "processo": d.get("processo", "N/A"),
                        "fornecedor": forn.get("nome", "Não informado"),
                        "cnpj_cpf": forn.get("cnpj_cpf_idgener", "N/A"),
                        "modalidade": d.get("modalidade", "Pregão"),
                        "objeto": d.get("objeto", ""),
                        "vigencia_inicio": d.get("vigencia_inicio"),
                        "vigencia_fim": fim_vig,
                        "dias_restantes": dias_rest,
                        "valor_global": converter_moeda(d.get("valor_global")),
                        "valor_acumulado": converter_moeda(d.get("valor_acumulado")),
                        "links": d.get("links", {})
                    })
                return pd.DataFrame(lista), None
            return pd.DataFrame(), f"Status API: {resp.status_code}"
        except Exception as e:
            return pd.DataFrame(), str(e)

    # Controles da Barra Lateral
    st.sidebar.divider()
    uasg_input = st.sidebar.text_input("Código UASG / UG:", value="102110")

    if st.sidebar.button("🔄 Sincronizar Bases"):
        st.cache_data.clear()
        st.rerun()

    # Indicador de Autenticação Oficial no Comprasnet
    st.sidebar.divider()
    st.sidebar.markdown("### 🏛️ Conexão Oficial Comprasnet")
    if st.session_state["token_comprasnet"]:
        st.sidebar.success(f"🟢 Operador Conectado: **{st.session_state['operador_comprasnet']}**")
        if st.sidebar.button("Desconectar Operador"):
            st.session_state["token_comprasnet"] = None
            st.session_state["operador_comprasnet"] = None
            st.rerun()
    else:
        st.sidebar.warning("⚪ Modo Consulta (Sem Operador Federal)")

    st.sidebar.divider()
    perfil_ativo = st.sidebar.radio(
        "Módulos e Visões de Trabalho:",
        [
            "🏛️ Alta Gestão & BI Executivo",
            "👔 Gestor do Contrato (Art. 117)",
            "📐 Fiscal Técnico (Medição / IMR / OS)",
            "💼 Fiscal Administrativo (DEMO / Terceirizados)",
            "💳 Operação Financeira & Faturas (Oficial Comprasnet)",
            "🛡️ Matriz de Riscos & Sanções (Art. 103 / 155)",
            "🔍 Raio-X Integrado & PDFs (360°)",
            "📑 Orçamento, RAP & Auditoria"
        ]
    )

    df_api, erro_api = fetch_comprasnet(uasg_input)
    df_meta = db_query("SELECT * FROM nllc_contratos")

    if not df_api.empty:
        if not df_meta.empty:
            df_completo = df_api.merge(df_meta, left_on="id", right_on="id_contrato", how="left")
        else:
            df_completo = df_api.copy()
            for col in ["tipo_regime", "tem_dedicacao_exclusiva", "data_base_reajuste", "valor_aditado_acumulado",
                        "publicado_pncp", "tipo_garantia", "vencimento_garantia", "status_gestao", "gestor_nome",
                        "fiscal_tecnico", "fiscal_administrativo", "anotacoes_gerais"]:
                df_completo[col] = None

        df_completo["tipo_regime"] = df_completo["tipo_regime"].fillna("SERVICO_CONTINUO")
        df_completo["tem_dedicacao_exclusiva"] = df_completo["tem_dedicacao_exclusiva"].fillna(0)
        df_completo["valor_aditado_acumulado"] = df_completo["valor_aditado_acumulado"].fillna(0.0)
        df_completo["publicado_pncp"] = df_completo["publicado_pncp"].fillna(1)
        df_completo["status_gestao"] = df_completo["status_gestao"].fillna("Vigente / Em Execução")
        df_completo["saldo_a_executar"] = df_completo["valor_global"] - df_completo["valor_acumulado"]
        df_completo["percentual_aditado"] = (df_completo["valor_aditado_acumulado"] / df_completo["valor_global"].replace(0, 1)) * 100
        
        def calc_farol(dias):
            if dias is None or pd.isna(dias): return "Indefinido"
            if dias < 0: return "🔴 Vencido"
            if dias <= 30: return "🚨 Crítico (≤ 30d)"
            if dias <= 90: return "⚠️ Atenção (≤ 90d)"
            return "🟢 Regular (> 90d)"
        df_completo["farol_prazo"] = df_completo["dias_restantes"].apply(calc_farol)
    else:
        df_completo = pd.DataFrame()

    hoje = datetime.now().date()

    # ==========================================================================
    # 1. ALTA GESTÃO & BI EXECUTIVO
    # ==========================================================================
    if perfil_ativo == "🏛️ Alta Gestão & BI Executivo":
        st.title(f"🏛️ Painel Estratégico — UASG {uasg_input}")
        st.caption("Visão Macrofinanceira, Governança de Gastos e Riscos Contratuais")
        
        if df_completo.empty:
            st.warning(f"Nenhum contrato ativo encontrado para a UASG {uasg_input}.")
        else:
            total_global = df_completo["valor_global"].sum()
            total_pago = df_completo["valor_acumulado"].sum()
            total_saldo = df_completo["saldo_a_executar"].sum()
            perc_exec = (total_pago / total_global * 100) if total_global > 0 else 0
            
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Contratos Ativos", len(df_completo))
            c2.metric("Valor Global", f"R$ {total_global:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
            c3.metric("Total Liquidado/Pago", f"R$ {total_pago:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."), f"{perc_exec:.1f}% Executado")
            c4.metric("Saldo a Executar", f"R$ {total_saldo:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
            
            st.divider()
            col_g1, col_g2 = st.columns(2)
            with col_g1:
                st.subheader("🚨 Controle de Prazos NLLC")
                st.bar_chart(df_completo["farol_prazo"].value_counts())
            with col_g2:
                st.subheader("📊 Distribuição por Modalidade")
                st.bar_chart(df_completo["modalidade"].value_counts())

            st.subheader("🏢 Top 5 Maiores Contratações da UASG")
            top5 = df_completo.nlargest(5, "valor_global")[["numero", "fornecedor", "modalidade", "valor_global", "saldo_a_executar", "vigencia_fim"]]
            st.dataframe(top5, use_container_width=True, hide_index=True)

    # ==========================================================================
    # 2. GESTOR DO CONTRATO (CORRIGIDO SEM DUPLICIDADES)
    # ==========================================================================
    elif perfil_ativo == "👔 Gestor do Contrato (Art. 117)":
        st.title("👔 Painel do Gestor do Contrato")
        if not df_completo.empty:
            opcoes = [f"Contrato {r['numero']} - {r['fornecedor']} (ID: {r['id']})" for _, r in df_completo.iterrows()]
            sel_contrato = st.selectbox("Selecione o Contrato para Gestão:", opcoes)
            id_sel = sel_contrato.split("ID: ")[-1].replace(")", "")
            item = df_completo[df_completo["id"] == id_sel].iloc[0]

            g_c1, g_c2, g_c3 = st.columns(3)
            perc_adit = item["percentual_aditado"]
            limite_max = 50.0 if item["tipo_regime"] == "OBRA_ENGENHARIA" else 25.0
            g_c1.metric("Aditivos Acumulados (Art. 125)", f"{perc_adit:.2f}%", f"Teto: {limite_max:.0f}%", delta_color="inverse" if perc_adit >= 20.0 else "normal")

            dt_base_obj = converter_data_segura(item.get("data_base_reajuste"))
            dias_base = (hoje - dt_base_obj).days if dt_base_obj else 0
            g_c2.metric(
               "Interregno de Reajuste (Art. 135)", 
               f"{dias_base} dias" if dt_base_obj else "Não Definido", 
               "Apto a Reajuste (≥ 1 ano)" if dias_base >= 365 else "Aguardando 1 ano" if dt_base_obj else "Data-base pendente",
               delta_color="normal" if dias_base >= 365 else "off"
            )

            dias_venc = item["dias_restantes"] or 0
            janela_120d = (item["tipo_regime"] == "SERVICO_CONTINUO") and (0 <= dias_venc <= 120)
            g_c3.metric("Janela de Prorrogação (120d)", f"{dias_venc} dias restantes", "🚨 Iniciar Prorrogação!" if janela_120d else "Regular")

            st.divider()
            st.markdown("<div class='alerta-local'>💾 <b>Ação Interna:</b> As alterações abaixo são salvas exclusivamente no banco de governança da sua UASG (não afetam a base do Comprasnet).</div>", unsafe_allow_html=True)
            
            with st.form(key=f"form_gestor_{id_sel}"):
                st.markdown("#### ⚙️ Parametrização Jurídica e Limites")
                col_f1, col_f2, col_f3 = st.columns(3)
                with col_f1:
                    novo_regime = st.selectbox(
                        "Regime Contratual:", 
                        ["SERVICO_CONTINUO", "FORNECIMENTO_ESCOPO", "OBRA_ENGENHARIA"], 
                        index=["SERVICO_CONTINUO", "FORNECIMENTO_ESCOPO", "OBRA_ENGENHARIA"].index(item["tipo_regime"]) if item["tipo_regime"] in ["SERVICO_CONTINUO", "FORNECIMENTO_ESCOPO", "OBRA_ENGENHARIA"] else 0,
                        key=f"regime_{id_sel}"
                    )
                    tem_demo = st.checkbox("Dedicação Exclusiva (DEMO)?", value=bool(item["tem_dedicacao_exclusiva"]), key=f"demo_{id_sel}")
                    status_gest = st.selectbox(
                        "Situação Local:", 
                        ["Vigente / Em Execução", "Em Renovação / Aditamento", "Sobrestado / Suspenso", "Em Notificação / Glosa", "Finalizado / Encerrado"], 
                        index=["Vigente / Em Execução", "Em Renovação / Aditamento", "Sobrestado / Suspenso", "Em Notificação / Glosa", "Finalizado / Encerrado"].index(item["status_gestao"]) if item["status_gestao"] in ["Vigente / Em Execução", "Em Renovação / Aditamento", "Sobrestado / Suspenso", "Em Notificação / Glosa", "Finalizado / Encerrado"] else 0,
                        key=f"status_{id_sel}"
                    )
                with col_f2:
                    dt_base_val = converter_data_segura(item.get("data_base_reajuste")) or date.today()
                    nova_dt_base = st.date_input("Data-Base do Reajuste:", value=dt_base_val, key=f"dt_base_{id_sel}")
                    novo_val_aditado = st.number_input("Valor Aditado (R$):", value=float(item["valor_aditado_acumulado"]), min_value=0.0, format="%.2f", key=f"val_aditado_{id_sel}")
                    publicado_pncp_val = st.checkbox("Publicado no PNCP?", value=bool(item["publicado_pncp"]), key=f"pncp_{id_sel}")
                with col_f3:
                    nome_gestor = st.text_input("Gestor:", value=str(item["gestor_nome"]) if item["gestor_nome"] else "", key=f"gestor_{id_sel}")
                    nome_fisc_tec = st.text_input("Fiscal Técnico:", value=str(item["fiscal_tecnico"]) if item["fiscal_tecnico"] else "", key=f"fisc_tec_{id_sel}")
                    nome_fisc_adm = st.text_input("Fiscal Administrativo:", value=str(item["fiscal_administrativo"]) if item["fiscal_administrativo"] else "", key=f"fisc_adm_{id_sel}")

                anotacoes_txt = st.text_area("Despachos / Diário de Bordo:", value=str(item["anotacoes_gerais"]) if item["anotacoes_gerais"] else "", key=f"anot_{id_sel}")

                if perfil_usuario == "editor":
                    if st.form_submit_button("💾 Salvar Parâmetros Internos"):
                        db_execute("""
                            INSERT OR REPLACE INTO nllc_contratos 
                            (id_contrato, tipo_regime, tem_dedicacao_exclusiva, data_base_reajuste, valor_aditado_acumulado,
                             publicado_pncp, status_gestao, gestor_nome, fiscal_tecnico, fiscal_administrativo, anotacoes_gerais)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (id_sel, novo_regime, int(tem_demo), nova_dt_base.strftime("%Y-%m-%d"), novo_val_aditado,
                              int(publicado_pncp_val), status_gest, nome_gestor, nome_fisc_tec, nome_fisc_adm, anotacoes_txt))
                        st.success("Salvo localmente com sucesso!")
                        st.cache_data.clear()
                        st.rerun()
                else:
                    st.info("🔒 Modo Somente Leitura (Consulta).")

    # ==========================================================================
    # 3. FISCAL TÉCNICO
    # ==========================================================================
    elif perfil_ativo == "📐 Fiscal Técnico (Medição / IMR / OS)":
        st.title("📐 Painel do Fiscal Técnico")
        if not df_completo.empty:
            opcoes_tec = [f"Contrato {r['numero']} - {r['fornecedor']} (ID: {r['id']})" for _, r in df_completo.iterrows()]
            sel_tec = st.selectbox("Selecione o Contrato:", opcoes_tec)
            id_tec = sel_tec.split("ID: ")[-1].replace(")", "")
            item_tec = df_completo[df_completo["id"] == id_tec].iloc[0]

            tab_med, tab_os, tab_oc = st.tabs(["📊 Medições & SLA/IMR", "📋 Ordens de Serviço (OS na API)", "📖 Livro de Ocorrências"])

            with tab_med:
                with st.form(f"form_med_{id_tec}"):
                    m1, m2 = st.columns(2)
                    with m1:
                        pref = st.text_input("Mês/Ano Ref:", placeholder="Ex: 08/2026")
                        sla = st.slider("SLA/IMR Atingido %:", 0.0, 100.0, 95.0)
                    with m2:
                        v_med = st.number_input("Valor Bruto Medido (R$):", min_value=0.0, format="%.2f")
                        v_glo = st.number_input("Valor Glosado (R$):", min_value=0.0, format="%.2f")
                    
                    if perfil_usuario == "editor":
                        if st.form_submit_button("💾 Salvar Medição Técnica (Interno)"):
                            db_execute("""
                                INSERT INTO nllc_medicoes_imr (id_contrato, periodo_ref, sla_percentual, valor_medido, valor_glosado, termo_provisorio_emitido, data_emissao_termo)
                                VALUES (?, ?, ?, ?, ?, 1, ?)
                            """, (id_tec, pref, sla, v_med, v_glo, datetime.now().strftime("%Y-%m-%d")))
                            st.success("Medição registrada!")
                            st.rerun()
                    else:
                        st.info("🔒 Modo Somente Leitura.")
                st.dataframe(db_query("SELECT * FROM nllc_medicoes_imr WHERE id_contrato = ?", params=(id_tec,)), use_container_width=True, hide_index=True)

            with tab_os:
                st.subheader("Ordens de Serviço e Fornecimento (API Comprasnet)")
                try:
                    r_os = requests.get(f"https://contratos.comprasnet.gov.br/api/v1/execucoes/contratos/{id_tec}", headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
                    if r_os.status_code == 200 and r_os.json():
                        st.dataframe(pd.DataFrame(r_os.json()), use_container_width=True)
                    else:
                        st.caption("Nenhuma Ordem de Serviço registrada na API para este contrato.")
                except:
                    st.caption("Não foi possível carregar as OS da API em tempo real.")

            with tab_oc:
                with st.form("form_oc"):
                    tipo_oc = st.selectbox("Tipo:", ["Notificação de Atraso", "Falha de Execução", "Descumprimento de SLA"])
                    desc_oc = st.text_area("Descrição:")
                    glosa_oc = st.number_input("Glosa Estimada (R$):", min_value=0.0, format="%.2f")
                    if perfil_usuario == "editor":
                        if st.form_submit_button("💾 Salvar no Livro Digital (Interno)"):
                            db_execute("""
                                INSERT INTO nllc_ocorrencias_sancoes (id_contrato, tipo_evento, data_registro, descricao, valor_glosa, status_processo)
                                VALUES (?, ?, ?, ?, ?, 'Registrado')
                            """, (id_tec, tipo_oc, datetime.now().strftime("%Y-%m-%d %H:%M"), desc_oc, glosa_oc))
                            st.success("Ocorrência salva!")
                            st.rerun()
                    else:
                        st.info("🔒 Modo Somente Leitura.")
                st.dataframe(db_query("SELECT * FROM nllc_ocorrencias_sancoes WHERE id_contrato = ?", params=(id_tec,)), use_container_width=True, hide_index=True)

    # ==========================================================================
    # 4. FISCAL ADMINISTRATIVO & TERCEIRIZADOS (IDEIA 1)
    # ==========================================================================
    elif perfil_ativo == "💼 Fiscal Administrativo (DEMO / Terceirizados)":
        st.title("💼 Fiscalização Administrativa e Terceirizados (DEMO)")
        if not df_completo.empty:
            opcoes_adm = [f"Contrato {r['numero']} - {r['fornecedor']} (ID: {r['id']})" for _, r in df_completo.iterrows()]
            sel_adm = st.selectbox("Selecione o Contrato:", opcoes_adm)
            id_adm = sel_adm.split("ID: ")[-1].replace(")", "")
            item_adm = df_completo[df_completo["id"] == id_adm].iloc[0]

            tab_cnds, tab_terceirizados = st.tabs(["🛡️ Trava de CNDs e Salários", "👥 Relação de Terceirizados (API Comprasnet)"])

            with tab_cnds:
                df_reg = db_query("SELECT * FROM nllc_regularidade_trabalhista WHERE id_contrato = ?", params=(id_adm,))
                reg_atual = df_reg.iloc[0] if not df_reg.empty else None

                with st.form(f"form_fiscal_adm_{id_adm}"):
                    col_a1, col_a2 = st.columns(2)
                    with col_a1:
                        cnd_fed = st.checkbox("CND Federal / Receita Válida?", value=bool(reg_atual["cnd_federal_valida"]) if reg_atual is not None else True)
                        cndt = st.checkbox("CNDT Trabalhista Válida?", value=bool(reg_atual["cndt_valida"]) if reg_atual is not None else True)
                        fgts = st.checkbox("CRF / FGTS Regular?", value=bool(reg_atual["fgts_valido"]) if reg_atual is not None else True)
                    with col_a2:
                        folha = st.checkbox("Folha e Benefícios Quitados?", value=bool(reg_atual["folha_salarios_paga"]) if reg_atual is not None else True)
                        trava = st.checkbox("🔒 BLOQUEAR / TRAVAR LIQUIDAÇÃO?", value=bool(reg_atual["trava_liquidacao"]) if reg_atual is not None else False)

                    if perfil_usuario == "editor":
                        if st.form_submit_button("💾 Salvar Parecer Fiscal (Interno)"):
                            db_execute("""
                                INSERT OR REPLACE INTO nllc_regularidade_trabalhista 
                                (id_contrato, cnd_federal_valida, cndt_valida, fgts_valido, folha_salarios_paga, trava_liquidacao)
                                VALUES (?, ?, ?, ?, ?, ?)
                            """, (id_adm, int(cnd_fed), int(cndt), int(fgts), int(folha), int(trava)))
                            st.success("Parecer atualizado localmente!")
                            st.rerun()
                    else:
                        st.info("🔒 Modo Somente Leitura.")

            with tab_terceirizados:
                st.subheader("Relação Nominal de Empregados Terceirizados Alocados")
                st.info("💡 **Ideia 1:** Utilize esta lista para conferir os postos de trabalho cobertos e a folha de pagamento enviada.")
                try:
                    r_terc = requests.get(f"https://contratos.comprasnet.gov.br/api/contrato/{id_adm}/terceirizados", headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
                    if r_terc.status_code == 200 and r_terc.json():
                        st.dataframe(pd.DataFrame(r_terc.json()), use_container_width=True)
                    else:
                        st.caption("Nenhum terceirizado cadastrado na API para este contrato.")
                except:
                    st.caption("Não foi possível carregar terceirizados em tempo real.")

    # ==========================================================================
    # 5. MÓDULO OPERACIONAL DE FATURAS & APROPRIAÇÃO
    # ==========================================================================
    elif perfil_ativo == "💳 Operação Financeira & Faturas (Oficial Comprasnet)":
        st.title("💳 Operação Financeira Direta no Comprasnet (Escrita Oficial)")
        st.caption("Apropriação de Faturas, Cancelamentos e Vinculação de Empenhos (SIASG/Governo Federal)")

        if not st.session_state["token_comprasnet"]:
            st.markdown("<div class='alerta-federal'>⚠️ <b>Acesso Operacional Restrito:</b> Para enviar comandos de apropriação e edição de faturas para o sistema do Governo Federal, faça login com seu usuário do Comprasnet/SIASG.</div>", unsafe_allow_html=True)
            with st.form("form_auth_comprasnet"):
                cpf_op = st.text_input("CPF do Operador Comprasnet:")
                senha_op = st.text_input("Senha do Comprasnet:", type="password")
                if st.form_submit_button("🔑 Autenticar no Comprasnet (POST /auth/login)"):
                    try:
                        r_auth = requests.post(
                            "https://contratos.comprasnet.gov.br/api/v1/auth/login",
                            json={"cpf": cpf_op, "password": senha_op},
                            headers={"Accept": "application/json"},
                            timeout=15
                        )
                        if r_auth.status_code == 200:
                            tok = r_auth.json().get("token") or r_auth.json().get("access_token")
                            st.session_state["token_comprasnet"] = tok
                            st.session_state["operador_comprasnet"] = cpf_op
                            st.success("✅ Autenticado no Comprasnet com sucesso!")
                            st.rerun()
                        else:
                            st.error(f"Erro na autenticação do Comprasnet (Status {r_auth.status_code}): {r_auth.text}")
                    except Exception as e:
                        st.error(f"Falha ao conectar com o Comprasnet: {e}")
        else:
            st.success(f"🔓 Sessão Ativa no Comprasnet como: `{st.session_state['operador_comprasnet']}`")
            
            aba_apropriar, aba_editar_fat, aba_cancelar_apr = st.tabs([
                "🔴 Apropriar Fatura / Pagamento",
                "🔴 Editar Situação de Fatura & Empenhos",
                "🔴 Cancelar / Excluir Apropriação"
            ])

            headers_comprasnet = {
                "Authorization": f"Bearer {st.session_state['token_comprasnet']}",
                "Accept": "application/json",
                "User-Agent": "Mozilla/5.0"
            }

            with aba_apropriar:
                st.markdown("<div class='alerta-federal'>⚠️ <b>ATENÇÃO: AÇÃO OFICIAL NO COMPRASNET</b><br>Ao clicar no botão abaixo, a fatura será apropriada oficialmente na base do Governo Federal para liquidação/pagamento.</div>", unsafe_allow_html=True)
                
                with st.form("form_apropriar_real"):
                    c_ap1, c_ap2 = st.columns(2)
                    with c_ap1:
                        c_id_apr = st.text_input("ID do Contrato:")
                        num_doc_apr = st.text_input("Número da Nota Fiscal / Fatura:")
                    with c_ap2:
                        val_apr = st.number_input("Valor da Apropriação (R$):", min_value=0.0, format="%.2f")
                        dt_apr = st.date_input("Data de Vencimento/Apropriação:", value=date.today())

                    confirm_apr = st.checkbox("Confirmo que verifiquei o ateste e desejo enviar a apropriação para a base federal.")

                    if st.form_submit_button("🚨 ENVIAR APROPRIAÇÃO AO COMPRASNET (POST /apropriar)"):
                        if not confirm_apr:
                            st.error("Por favor, marque a caixa de confirmação antes de executar a ação oficial.")
                        else:
                            try:
                                payload = {
                                    "contrato_id": c_id_apr,
                                    "numero_documento": num_doc_apr,
                                    "valor": val_apr,
                                    "data": dt_apr.strftime("%Y-%m-%d")
                                }
                                r_post = requests.post("https://contratos.comprasnet.gov.br/api/v1/contrato/instrumento_cobranca/apropriar", json=payload, headers=headers_comprasnet, timeout=15)
                                if r_post.status_code in [200, 201]:
                                    st.success("✅ Apropriação realizada com sucesso no Comprasnet!")
                                else:
                                    st.error(f"Erro do Comprasnet ({r_post.status_code}): {r_post.text}")
                            except Exception as e:
                                st.error(f"Falha na requisição: {e}")

            with aba_editar_fat:
                st.markdown("<div class='alerta-federal'>⚠️ <b>ATENÇÃO: AÇÃO OFICIAL NO COMPRASNET</b><br>Esta operação altera a situação da fatura e seus empenhos vinculados no SIASG.</div>", unsafe_allow_html=True)
                
                with st.form("form_edit_fat"):
                    ef_col1, ef_col2 = st.columns(2)
                    with ef_col1:
                        fat_id = st.text_input("ID da Fatura no Comprasnet:")
                        just_id = st.text_input("ID da Justificativa:")
                    with ef_col2:
                        sit_id = st.selectbox("Nova Situação da Fatura:", ["1 - Aprovada", "2 - Glosada", "3 - Rejeitada", "4 - Em Liquidação"])
                        empenhos_list = st.text_input("Lista de Empenhos (separados por vírgula):")

                    confirm_fat = st.checkbox("Confirmo a alteração da situação da fatura na base federal.")

                    if st.form_submit_button("🚨 ATUALIZAR FATURA NO COMPRASNET (PUT /faturas/edit)"):
                        if not confirm_fat:
                            st.error("Marque a confirmação antes de enviar.")
                        else:
                            url_put = f"https://contratos.comprasnet.gov.br/api/v1/contrato/faturas/edit/id_fatura/{fat_id}/justificativa/{just_id}/situacao/{sit_id.split(' - ')[0]}/empenhos"
                            try:
                                r_put = requests.put(url_put, json={"empenhos": empenhos_list.split(",")}, headers=headers_comprasnet, timeout=15)
                                if r_put.status_code == 200:
                                    st.success("✅ Fatura atualizada com sucesso no Comprasnet!")
                                else:
                                    st.error(f"Erro ({r_put.status_code}): {r_put.text}")
                            except Exception as e:
                                st.error(f"Erro: {e}")

            with aba_cancelar_apr:
                st.markdown("<div class='alerta-federal'>⚠️ <b>ATENÇÃO: AÇÃO CRÍTICA NO COMPRASNET</b><br>Cancelar ou excluir uma apropriação remove o registro financeiro na base oficial do Governo Federal.</div>", unsafe_allow_html=True)
                with st.form("form_canc_apr"):
                    id_apr_canc = st.text_input("ID da Apropriação:")
                    motivo_canc = st.text_area("Justificativa do Cancelamento:")
                    confirm_canc = st.checkbox("Estou ciente e confirmo o cancelamento da apropriação na base federal.")

                    if st.form_submit_button("🚨 CANCELAR APROPRIAÇÃO (PUT /apropriacao/cancelar)"):
                        if not confirm_canc:
                            st.error("Marque a confirmação para prosseguir.")
                        else:
                            try:
                                r_canc = requests.put("https://contratos.comprasnet.gov.br/api/v1/contrato/apropriacao/cancelar", json={"id": id_apr_canc, "justificativa": motivo_canc}, headers=headers_comprasnet, timeout=15)
                                if r_canc.status_code == 200:
                                    st.success("✅ Apropriação cancelada com sucesso no Comprasnet!")
                                else:
                                    st.error(f"Erro ({r_canc.status_code}): {r_canc.text}")
                            except Exception as e:
                                st.error(f"Erro: {e}")

    # ==========================================================================
    # 6. MATRIZ DE RISCOS & SANÇÕES / IMPEDIMENTOS
    # ==========================================================================
    elif perfil_ativo == "🛡️ Matriz de Riscos & Sanções (Art. 103 / 155)":
        st.title("🛡️ Matriz de Riscos e Consulta de Impedimentos")
        
        tab_r_int, tab_r_imp = st.tabs(["🎯 Matriz de Riscos (Interna - SQLite)", "🔍 Verificar Impedimentos (API Comprasnet)"])

        with tab_r_int:
            st.markdown("<div class='alerta-local'>💾 <b>Ação Interna:</b> A Matriz de Riscos é mantida no banco da sua UASG conforme o Art. 103 da Lei 14.133/2021.</div>", unsafe_allow_html=True)
            if not df_completo.empty:
                sel_r = st.selectbox("Selecione o Contrato:", [f"Contrato {r['numero']} - {r['fornecedor']} (ID: {r['id']})" for _, r in df_completo.iterrows()])
                id_r = sel_r.split("ID: ")[-1].replace(")", "")

                with st.form("form_risco"):
                    r1, r2 = st.columns(2)
                    with r1:
                        ev_risco = st.text_input("Evento de Risco:", placeholder="Ex: Inadimplemento contratual")
                        prob = st.selectbox("Probabilidade:", ["Baixa", "Média", "Alta"])
                    with r2:
                        imp = st.selectbox("Impacto:", ["Baixo", "Médio", "Alto"])
                        mitig = st.text_area("Ação Mitigadora:")

                    if perfil_usuario == "editor":
                        if st.form_submit_button("💾 Salvar Risco na Matriz (Interno)"):
                            db_execute("""
                                INSERT INTO nllc_matriz_riscos (id_contrato, evento_risco, probabilidade, impacto, acao_mitigadora, responsavel)
                                VALUES (?, ?, ?, ?, ?, 'Contratada')
                            """, (id_r, ev_risco, prob, imp, mitig))
                            st.success("Risco cadastrado localmente!")
                            st.rerun()
                    else:
                        st.info("🔒 Modo Somente Leitura.")

                st.dataframe(db_query("SELECT * FROM nllc_matriz_riscos WHERE id_contrato = ?", params=(id_r,)), use_container_width=True, hide_index=True)

        with tab_r_imp:
            st.subheader("Verificação de Impedimentos em Compras (POST /comprasnet/compras/impedimentos)")
            with st.form("form_imp"):
                itens_verif = st.text_input("IDs dos Itens de Compra (separados por vírgula):")
                if st.form_submit_button("🔍 Consultar Impedimentos na Base Federal"):
                    try:
                        r_imp = requests.post("https://contratos.comprasnet.gov.br/api/v1/comprasnet/compras/impedimentos", json={"itens": itens_verif.split(",")}, headers={"Accept": "application/json"}, timeout=15)
                        if r_imp.status_code == 200:
                            st.dataframe(pd.DataFrame(r_imp.json()), use_container_width=True)
                        else:
                            st.info("Nenhum impedimento retornado pela API para estes itens.")
                    except Exception as e:
                        st.error(f"Erro na consulta: {e}")

    # ==========================================================================
    # 7. RAIO-X INTEGRADO & BAIXAR PDFS COM 1 CLIQUE
    # ==========================================================================
    elif perfil_ativo == "🔍 Raio-X Integrado & PDFs (360°)":
        st.title("🔍 Raio-X 360° do Contrato (Consultas ao Vivo)")
        if not df_completo.empty:
            sel_rx = st.selectbox("Escolha o Contrato:", [f"Contrato {r['numero']} - {r['fornecedor']} (ID: {r['id']})" for _, r in df_completo.iterrows()])
            id_rx = sel_rx.split("ID: ")[-1].replace(")", "")
            rx = df_completo[df_completo["id"] == id_rx].iloc[0]

            st.markdown(f"### Contrato nº `{rx['numero']}` — {rx['fornecedor']}")
            st.markdown(f"**Objeto:** {rx['objeto']}")

            rx_aba1, rx_aba2, rx_aba3, rx_aba4, rx_aba5, rx_aba6 = st.tabs([
                "📄 Arquivos & Download de PDFs (Ideia 3)",
                "📦 Itens e Quantitativos",
                "💳 Faturas & Pagamentos",
                "🌳 Árvore de Aditivos / Histórico",
                "🛡️ Apólices / Garantias",
                "💰 Empenhos Vinculados"
            ])

            links = rx.get("links", {}) if isinstance(rx.get("links"), dict) else {}

            with rx_aba1:
                st.subheader("Documentos e Contratos Digitalizados (GET /arquivos)")
                if "arquivos" in links:
                    try:
                        r = requests.get(links["arquivos"], headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
                        if r.status_code == 200 and r.json():
                            df_arq = pd.DataFrame(r.json())
                            st.dataframe(df_arq, use_container_width=True)
                            for _, arq in df_arq.iterrows():
                                link_pdf = arq.get("url") or arq.get("link") or arq.get("path")
                                nome_pdf = arq.get("nome") or arq.get("descricao") or "Documento"
                                if link_pdf:
                                    st.markdown(f"👉 [📄 **Baixar {nome_pdf} em PDF**]({link_pdf})")
                        else:
                            st.caption("Nenhum arquivo em PDF vinculado.")
                    except:
                        st.caption("Erro ao carregar arquivos da API.")

            with rx_aba2:
                if "itens" in links:
                    try:
                        r = requests.get(links["itens"], headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
                        if r.status_code == 200 and r.json(): st.dataframe(pd.DataFrame(r.json()), use_container_width=True)
                        else: st.caption("Nenhum item discriminado.")
                    except: st.caption("Erro ao carregar itens.")

            with rx_aba3:
                if "faturas" in links:
                    try:
                        r = requests.get(links["faturas"], headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
                        if r.status_code == 200 and r.json(): st.dataframe(pd.DataFrame(r.json()), use_container_width=True)
                        else: st.caption("Nenhuma fatura registrada.")
                    except: st.caption("Erro ao carregar faturas.")

            with rx_aba4:
                if "historico" in links:
                    try:
                        r = requests.get(links["historico"], headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
                        if r.status_code == 200 and r.json(): st.dataframe(pd.DataFrame(r.json()), use_container_width=True)
                        else: st.caption("Nenhum histórico/aditivo registrado.")
                    except: st.caption("Erro ao carregar histórico.")

            with rx_aba5:
                if "garantias" in links:
                    try:
                        r = requests.get(links["garantias"], headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
                        if r.status_code == 200 and r.json(): st.dataframe(pd.DataFrame(r.json()), use_container_width=True)
                        else: st.caption("Nenhuma garantia registrada.")
                    except: st.caption("Erro ao carregar garantias.")

            with rx_aba6:
                if "empenhos" in links:
                    try:
                        r = requests.get(links["empenhos"], headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
                        if r.status_code == 200 and r.json(): st.dataframe(pd.DataFrame(r.json()), use_container_width=True)
                        else: st.caption("Nenhum empenho vinculado.")
                    except: st.caption("Erro ao carregar empenhos.")

    # ==========================================================================
    # 8. ORÇAMENTO, RAP (IDEIA 2) & AUDITORIA EXCEL
    # ==========================================================================
    elif perfil_ativo == "📑 Orçamento, RAP & Auditoria":
        st.title("📑 Painel Orçamentário, Restos a Pagar (RAP) e Auditoria")
        
        tab_rap, tab_export = st.tabs(["💰 Restos a Pagar da UASG (RAP - Ideia 2)", "📑 Exportação Consolidada para Auditoria"])

        with tab_rap:
            st.subheader(f"Restos a Pagar da UASG {uasg_input} (GET /empenho/rp)")
            st.info("💡 **Ideia 2:** Monitore os saldos empenhados e restos a pagar para evitar cancelamento orçamentário no encerramento do exercício.")
            try:
                r_rap = requests.get("https://contratos.comprasnet.gov.br/api/v1/empenho/rp", headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
                if r_rap.status_code == 200 and r_rap.json():
                    st.dataframe(pd.DataFrame(r_rap.json()), use_container_width=True)
                else:
                    st.caption("Nenhum Resto a Pagar encontrado ou consulta indisponível.")
            except:
                st.caption("Não foi possível carregar os Restos a Pagar.")

        with tab_export:
            st.subheader("Gerar Planilha de Auditoria e Prestação de Contas")
            if not df_completo.empty:
                buffer = io.BytesIO()
                with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                    df_completo.to_excel(writer, index=False, sheet_name='Contratos_NLLC')
                    db_query("SELECT * FROM nllc_matriz_riscos").to_excel(writer, index=False, sheet_name='Matriz_Riscos')
                    db_query("SELECT * FROM nllc_ocorrencias_sancoes").to_excel(writer, index=False, sheet_name='Livro_Ocorrencias')
                    db_query("SELECT * FROM nllc_medicoes_imr").to_excel(writer, index=False, sheet_name='Medicoes_IMR')

                st.download_button(
                    label="📥 Baixar Relatório Completo NLLC (.xlsx)",
                    data=buffer.getvalue(),
                    file_name=f"auditoria_nllc_uasg_{uasg_input}_{datetime.now().strftime('%Y%m%d')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

# ==============================================================================
# DISPARADOR DO SISTEMA
# ==============================================================================
if not st.session_state["autenticado"]:
    render_tela_login()
else:
    render_painel_principal()

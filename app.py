# ═══════════════════════════════════════════════════════════════
# MÓDULO 2: APERTURA DE CUENTAS FCI (DISEÑO PREMIUM EDITABLE)
# ═══════════════════════════════════════════════════════════════
elif modulo == "📂 Apertura de Cuentas":
    
    # Hero de encabezado corporativo
    st.markdown("""
    <div class="novus-hero">
      <div class="novus-eyebrow">middle office · onboarding</div>
      <h1>seguimiento y <span>apertura de cuentas</span> fci</h1>
      <p>Gestión de trámites comitentes en ALyCs y cuentas remuneradas bancarias en tiempo real.</p>
    </div>
    """, unsafe_allow_html=True)

    EXCEL_PATH = "seguimiento_cuentas.xlsx"

    @st.cache_data
    def load_aperturas_raw():
        try:
            df_c = pd.read_excel(EXCEL_PATH, sheet_name='Cuentas comitentes')
            df_r = pd.read_excel(EXCEL_PATH, sheet_name='Cuentas remuneradas')
            df_f = pd.read_excel(EXCEL_PATH, sheet_name='Lista FCI')
            return df_c, df_r, df_f
        except Exception as e:
            st.error(f"Error al cargar la base de datos de cuentas: {e}")
            return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    df_com, df_rem, df_fci = load_aperturas_raw()

    if not df_com.empty:
        # Métricas limpias consolidando ambas carpetas
        tot_com = len(df_com.dropna(subset=['Estado']))
        tot_rem = len(df_rem.dropna(subset=['Estado']))
        tot_general = tot_com + tot_rem

        abiertas_com = (df_com['Estado'] == 'Abierta').sum()
        abiertas_rem = (df_rem['Estado'] == 'Abierta').sum()
        abiertas_total = abiertas_com + abiertas_rem

        proc_com = (df_com['Estado'] == 'En proceso').sum()
        proc_rem = (df_rem['Estado'] == 'En proceso').sum()
        proc_total = proc_com + proc_rem

        pct_efectividad = (abiertas_total / tot_general * 100) if tot_general > 0 else 0

        # Tarjetas KPI con diseño estilizado
        k1, k2, k3, k4 = st.columns(4)
        with k1:
            st.markdown(f'<div class="kpi-card accent"><div class="kpi-label">Total Solicitudes</div><div class="kpi-value">{tot_general:,}</div><div class="kpi-sub">Comitentes + Remuneradas</div></div>', unsafe_allow_html=True)
        with k2:
            st.markdown(f'<div class="kpi-card"><div class="kpi-label">Cuentas Operativas</div><div class="kpi-value">{abiertas_total:,}</div><div class="kpi-delta pos">▲ {pct_efectividad:.1f}% efectividad</div></div>', unsafe_allow_html=True)
        with k3:
            st.markdown(f'<div class="kpi-card"><div class="kpi-label">Trámites En Proceso</div><div class="kpi-value sm" style="color:#E05555">{proc_total:,}</div><div class="kpi-sub">Pendientes de confirmación</div></div>', unsafe_allow_html=True)
        with k4:
            st.markdown(f'<div class="kpi-card"><div class="kpi-label">Cobertura Bancos / ALyCs</div><div class="kpi-value sm">{df_com["Contraparte"].nunique() + df_rem["Contraparte"].nunique()}</div><div class="kpi-sub">Entidades registradas</div></div>', unsafe_allow_html=True)

        st.markdown("<div style='height:15px'></div>", unsafe_allow_html=True)

        # Navegación interna por Solapas Ejecutivas
        tab_com, tab_rem, tab_cnv = st.tabs([
            "  💼 Cuentas Comitentes (ALyCs)  ", 
            "  🏦 Cuentas Remuneradas (Bancos)  ", 
            "  📜 Mapeo CNV  "
        ])

        with tab_com:
            st.markdown('<div class="chart-label">Edición directa de Comitentes por ALyC</div>', unsafe_allow_html=True)
            st.caption("💡 Hacé doble clic sobre cualquier fila o usá el desplegable para modificar estados y números de cuenta.")

            edited_com = st.data_editor(
                df_com,
                column_config={
                    "Estado": st.column_config.SelectboxColumn("Estado", options=["Abierta", "En proceso"], required=True, width="medium"),
                    "Tipo de cuenta": st.column_config.TextColumn("Tipo", width="small"),
                    "Contraparte": st.column_config.TextColumn("Contraparte / ALyC", width="medium"),
                    "FCI": st.column_config.TextColumn("Fondo FCI", width="medium"),
                    "N° de Cuenta": st.column_config.TextColumn("N° Comitente", width="small"),
                    "Observaciones": st.column_config.TextColumn("Observaciones", width="large"),
                    "Comentarios": st.column_config.TextColumn("Comentarios", width="large"),
                },
                num_rows="dynamic",
                use_container_width=True,
                hide_index=True,
                key="editor_comitentes_prod"
            )

            col_btn, _ = st.columns([1, 4])
            with col_btn:
                if st.button("💾 Guardar Cambios Comitentes"):
                    try:
                        with pd.ExcelWriter(EXCEL_PATH, engine="openpyxl") as writer:
                            edited_com.to_excel(writer, sheet_name='Cuentas comitentes', index=False)
                            df_rem.to_excel(writer, sheet_name='Cuentas remuneradas', index=False)
                            df_fci.to_excel(writer, sheet_name='Lista FCI', index=False)
                        st.cache_data.clear()
                        st.success("✅ ¡Cambios guardados en el sistema!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error al guardar: {e}")

        with tab_rem:
            st.markdown('<div class="chart-label">Edición directa de Cuentas Remuneradas Bancarias</div>', unsafe_allow_html=True)
            
            edited_rem = st.data_editor(
                df_rem,
                column_config={
                    "Estado": st.column_config.SelectboxColumn("Estado", options=["Abierta", "En proceso"], required=True, width="medium"),
                    "Fecha de Solicitud": st.column_config.DateColumn("Fecha Solicitud", format="DD/MM/YYYY"),
                    "Contraparte": st.column_config.TextColumn("Banco / Entidad", width="medium"),
                    "Fondo": st.column_config.TextColumn("Fondo", width="medium"),
                    "Observaciones": st.column_config.TextColumn("Observaciones", width="large"),
                },
                num_rows="dynamic",
                use_container_width=True,
                hide_index=True,
                key="editor_remuneradas_prod"
            )

            col_btn2, _ = st.columns([1, 4])
            with col_btn2:
                if st.button("💾 Guardar Cambios Remuneradas"):
                    try:
                        with pd.ExcelWriter(EXCEL_PATH, engine="openpyxl") as writer:
                            df_com.to_excel(writer, sheet_name='Cuentas comitentes', index=False)
                            edited_rem.to_excel(writer, sheet_name='Cuentas remuneradas', index=False)
                            df_fci.to_excel(writer, sheet_name='Lista FCI', index=False)
                        st.cache_data.clear()
                        st.success("✅ ¡Cambios guardados en el sistema!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error al guardar: {e}")

        with tab_cnv:
            st.markdown('<div class="chart-label">Matrículas e Identificadores CNV</div>', unsafe_allow_html=True)
            st.dataframe(df_fci.dropna(subset=['Fondo']), use_container_width=True, hide_index=True)

    # Pie de página corporativo
    st.markdown(f"""
    <div style="background:#1A1C1A; margin: 2rem -1rem -1rem -1rem; padding: 16px 36px; display:flex; justify-content:space-between; align-items:center;">
      <div style="color:#5DBB63; font-size:.85rem; font-weight:600;">novus <span style="color:#9AADA9; font-weight:300;">asset management</span></div>
      <div style="color:#777; font-size:.7rem;">middle office · módulo onboarding & aperturas</div>
    </div>
    """, unsafe_allow_html=True)

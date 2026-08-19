from datetime import datetime, timedelta, timezone
import pandas as pd
from sqlalchemy import text
import streamlit as st
from Conexion import obtener_conexion

# ==============================================================================
# CONFIGURACIÓN DE PÁGINA
# ==============================================================================
st.set_page_config(
    page_title='Control de Pasillos - Prefectura',
    page_icon='👮',
    layout='centered',
    initial_sidebar_state='collapsed',
)


# ==============================================================================
# FUNCIONES AUXILIARES
# ==============================================================================
def obtener_fecha_hora_mexico():
    """Retorna fecha y hora actual en zona horaria UTC-6 (Centro de México)."""
    tz_mex = timezone(timedelta(hours=-6))
    ahora = datetime.now(tz_mex)
    return ahora.strftime('%Y-%m-%d'), ahora.strftime('%H:%M:%S')


# ==============================================================================
# APLICACIÓN PRINCIPAL DE PREFECTURA
# ==============================================================================
def app_prefectura():
    engine = obtener_conexion()

    st.title('👮 Control de Pasillos - Prefectura')

    # ------------------------------------------------------------------
    # 1. ESTADO DE SESIÓN Y LOGIN SOLO POR CONTRASEÑA
    # ------------------------------------------------------------------
    if 'gestor_autenticado' not in st.session_state:
        st.session_state['gestor_autenticado'] = False
        st.session_state['idGestor'] = None
        st.session_state['nombre'] = ''
        st.session_state['puesto'] = ''

    # Inicialización de estados para los widgets y flujo de reinicio
    if 'alumnos_reporte_sel' not in st.session_state:
        st.session_state['alumnos_reporte_sel'] = []

    if 'reset_alumnos' not in st.session_state:
        st.session_state['reset_alumnos'] = False

    if not st.session_state['gestor_autenticado']:
        st.subheader('🔐 Acceso a Prefectura')

        with st.form('form_login_prefecto'):
            pwd_input = st.text_input('🔑 Contraseña:', type='password')
            btn_ingresar = st.form_submit_button(
                '🔓 Ingresar al Sistema', type='primary', use_container_width=True
            )

            if btn_ingresar:
                if not pwd_input.strip():
                    st.warning('⚠️ Ingresa tu contraseña.')
                else:
                    try:
                        query_valida = text("""
                            SELECT idGestor, nombre, puesto 
                            FROM gestor 
                            WHERE LTRIM(RTRIM(Password)) = :pwd 
                              AND activo = 1
                        """)
                        with engine.connect() as conn:
                            res = conn.execute(
                                query_valida, {'pwd': pwd_input.strip()}
                            ).fetchone()

                            if res:
                                st.session_state['gestor_autenticado'] = True
                                st.session_state['idGestor'] = res.idGestor
                                st.session_state['nombre'] = res.nombre
                                st.session_state['puesto'] = res.puesto
                                st.rerun()
                            else:
                                st.error('❌ Contraseña incorrecta.')
                    except Exception as err_g:
                        st.error(f'⚠️ Error al conectar con la base de datos: {err_g}')

        st.stop()

    # ------------------------------------------------------------------
    # 2. BARRA DE SESIÓN ACTIVA
    # ------------------------------------------------------------------
    col_info, col_logout = st.columns([3, 1])
    with col_info:
        st.info(
            f"👤 **Prefecto activo:** {st.session_state['nombre']} ("
            f"{st.session_state['puesto']})"
        )
    with col_logout:
        if st.button('🔒 Salir', use_container_width=True):
            st.session_state['gestor_autenticado'] = False
            st.rerun()

    st.divider()

    # ------------------------------------------------------------------
    # 3. CAPTURA DE REPORTES DE PASILLO
    # ------------------------------------------------------------------
    try:
        with engine.connect() as conn:
            df_grupos = pd.read_sql(
                text('SELECT DISTINCT LTRIM(RTRIM(grupo)) as grupo FROM alumno ORDER BY grupo'),
                conn,
            )
            df_lugares = pd.read_sql(
                text('SELECT idlugar, nombre FROM lugar ORDER BY nombre'), conn
            )
            df_actividades = pd.read_sql(
                text('SELECT idactividad, nombre FROM Actividad ORDER BY nombre'),
                conn,
            )

            # Consulta base ordenada alfabéticamente por nombre de alumno
            df_alumnos_base = pd.read_sql(
                text(
                    'SELECT idalumno, nombre, LTRIM(RTRIM(grupo)) as grupo, '
                    " (CAST(idalumno AS VARCHAR) + ' - ' + nombre + ' (' + "
                    " LTRIM(RTRIM(grupo)) + ')') as etiqueta "
                    'FROM alumno ORDER BY nombre ASC'
                ),
                conn,
            )

        # A. Selección de Alumnos
        st.subheader('1️⃣ Selección de Alumnos')

        # Si venimos de guardar un reporte, limpiamos la selección ANTES de instanciar el widget
        if st.session_state.get('reset_alumnos'):
            st.session_state['alumnos_reporte_sel'] = []
            st.session_state['reset_alumnos'] = False

        # Filtro multiselección por Grupo(s)
        grupos_sel = st.multiselect(
            '🏫 Filtrar por Grupo(s):',
            options=df_grupos['grupo'].tolist(),
            placeholder='Selecciona uno o varios grupos (deja vacío para ver todos)...',
        )

        # Filtrar alumnos manteniendo el orden alfabético
        if grupos_sel:
            df_filtrado = df_alumnos_base[df_alumnos_base['grupo'].isin(grupos_sel)]
        else:
            df_filtrado = df_alumnos_base

        ids_filtrados = df_filtrado['idalumno'].tolist()

        # Combinar opciones manteniendo el orden alfabético original de df_alumnos_base
        ids_totales_set = set(
            ids_filtrados + st.session_state['alumnos_reporte_sel']
        )
        df_opciones = df_alumnos_base[
            df_alumnos_base['idalumno'].isin(ids_totales_set)
        ]
        opciones_disponibles = df_opciones['idalumno'].tolist()

        # Diccionario para formatear la etiqueta del alumno
        dict_alumnos_etiqueta = dict(
            zip(df_alumnos_base['idalumno'], df_alumnos_base['etiqueta'])
        )

        # Multiselect de Alumnos (Sin parámetro 'default' para evitar conflicto con 'key')
        alumnos_seleccionados = st.multiselect(
            '👥 Selecciona el/los Alumno(s) a reportar:',
            options=opciones_disponibles,
            format_func=lambda id_al: dict_alumnos_etiqueta.get(
                id_al, str(id_al)
            ),
            key='alumnos_reporte_sel',
            placeholder='Escribe o selecciona uno o varios alumnos...',
        )

        st.divider()

        # B. Detalles del Incidente
        st.subheader('2️⃣ Detalles de la Incidencia')
        c_lugar, c_act = st.columns(2)

        with c_lugar:
            dict_lugares = dict(zip(df_lugares['nombre'], df_lugares['idlugar']))
            lugar_sel = st.selectbox(
                '📍 Lugar del hallazgo:', list(dict_lugares.keys())
            )
            id_lugar_sel = dict_lugares[lugar_sel]

        with c_act:
            dict_act = dict(
                zip(df_actividades['nombre'], df_actividades['idactividad'])
            )
            act_sel = st.selectbox('🎯 Actividad detectada:', list(dict_act.keys()))
            id_act_sel = dict_act[act_sel]

        conducta_sel = st.radio(
            '🏷️ Evaluar Conducta:',
            ['🟢 Buena', '🔴 Mala'],
            horizontal=True,
            index=0,
        )
        # Mapeo a entero (INTEGER): 1 = Buena, 0 = Mala
        val_conducta = 1 if 'Buena' in conducta_sel else 0

        st.divider()

        # C. Registro en Base de Datos
        if st.button(
            '📝 Guardar Reporte en Prefectura',
            type='primary',
            use_container_width=True,
        ):
            if not alumnos_seleccionados:
                st.warning('⚠️ Selecciona al menos un alumno para guardar.')
            else:
                fecha_act, hora_act = obtener_fecha_hora_mexico()

                query_insert = text("""
                    INSERT INTO prefectura (fecha, hora, idalumno, idActividad, idLugar, idGestor, conducta)
                    VALUES (:fecha, :hora, :idalumno, :idActividad, :idLugar, :idGestor, :conducta)
                """)

                with engine.begin() as conn:
                    for id_al in alumnos_seleccionados:
                        conn.execute(
                            query_insert,
                            {
                                'fecha': fecha_act,
                                'hora': hora_act,
                                'idalumno': id_al,
                                'idActividad': id_act_sel,
                                'idLugar': id_lugar_sel,
                                'idGestor': st.session_state['idGestor'],
                                'conducta': val_conducta,
                            },
                        )

                # Notificación flotante de confirmación
                st.toast(
                    f'✅ ¡Éxito! Se registraron {len(alumnos_seleccionados)} reporte(s) en {lugar_sel}.',
                    icon='🎉'
                )

                # Activamos la bandera para limpiar la lista en el siguiente renderizado y recargamos
                st.session_state['reset_alumnos'] = True
                st.rerun()

    except Exception as err:
        st.error(f'⚠️ Error al procesar datos: {err}')


# ==============================================================================
# EJECUCIÓN DIRECTA
# ==============================================================================
if __name__ == '__main__':
    app_prefectura()

"""
main.py — Punto de entrada del Auto DayTrading Bot.

Ejecuta este archivo para iniciar el bot:
    python main.py

Módulos activos:
    [✓] Módulo 1: Setup y Conexión         (broker.py)
    [✓] Módulo 2: Motor de Datos           (data_feed.py — velas de 15 min)
    [✓] Módulo 3: Motor de Análisis        (analysis.py — EMA9/21 + RSI14)
    [✓] Módulo 4: Ejecución y Riesgo       (execution.py — fracciones + SL/TP)
    [✓] Módulo 5: Sentimiento de Noticias  (sentiment.py — Alpaca News + Claude Haiku)

Scheduler (hora ET, respeta DST automáticamente):
    09:35 ET     → Análisis completo + posible compra (apertura de mercado)
    12:30 ET     → Análisis completo + posible compra o cierre (mediodía)
    cada 30 min  → Solo monitoreo de SL/TP de posiciones abiertas

Diseño para Cash Account T+1:
    Con liquidación al día siguiente no tiene sentido operar cada 5 minutos.
    Dos ventanas de análisis al día son suficientes; el monitoreo frecuente
    de SL/TP protege las posiciones entre esas ventanas.

Principios SOLID aplicados:
    SRP — TradingBot encapsula el estado (clientes, config). Los ciclos
          son métodos con responsabilidad única: monitorear o analizar.
    DIP — TradingBot recibe AppConfig en su constructor; no llama get_config()
          internamente en cada método.
"""

import os
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

import schedule
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from alpaca.trading.client import TradingClient

from src.analysis import Signal, calculate_indicators, get_signal, print_analysis
from src.broker import (
    get_available_cash,
    get_clients,
    is_market_open,
    print_account_summary,
)
from src.config import AppConfig, get_config
from src.data_feed import get_historical_bars, get_latest_bar, print_latest_bar
from src.execution import ejecutar_senal, get_posiciones_abiertas, monitorear_sl_tp
from src.notifier import notify_cycle, notify_error, notify_shutdown, notify_startup
from src.sentiment import get_sentiment, print_sentiment
from src.services.universe_service import build_daily_universe

# ─── Configuración del bot ───────────────────────────────────────────────────

ET = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class AnalysisSlot:
    name: str
    hour: int
    minute: int


@dataclass(frozen=True)
class BotSettings:
    symbols: list[str]
    timeframe: TimeFrame
    days_back: int
    timezone: ZoneInfo
    analysis_slots: tuple[AnalysisSlot, ...]


DEFAULT_SETTINGS = BotSettings(
    symbols=["SPY", "AAPL", "TSLA", "NVDA"],
    timeframe=TimeFrame(15, TimeFrameUnit.Minute),
    days_back=5,  # ~130 velas (26 por dia x 5 dias)
    timezone=ET,
    analysis_slots=(
        AnalysisSlot(name="apertura", hour=9, minute=35),
        AnalysisSlot(name="mediodia", hour=12, minute=30),
    ),
)


# ─── Clase principal ─────────────────────────────────────────────────────────

class TradingBot:
    """Encapsula el estado y la lógica del bot de trading.

    Elimina las variables globales de la versión anterior y agrupa en un
    solo objeto todo lo necesario para operar: clientes de API, configuración
    y el registro de ciclos ejecutados hoy (SRP).

    Uso:
        bot = TradingBot.create()   # conecta y valida credenciales
        bot.run()                   # lanza el scheduler (bloqueante)
    """

    def __init__(
        self,
        config: AppConfig,
        trading_client: TradingClient,
        data_client: StockHistoricalDataClient,
        settings: BotSettings = DEFAULT_SETTINGS,
    ) -> None:
        self.config         = config
        self.trading_client = trading_client
        self.data_client    = data_client
        self.settings       = settings
        self._ejecutados_hoy: set[str] = set()
        self._dia_actual: date | None = None
        self._universo: list[str] = list(settings.symbols)

    # ─── Constructor alternativo (factory) ───────────────────────────────────

    @classmethod
    def create(cls) -> "TradingBot":
        """Carga la configuración, conecta con Alpaca y retorna el bot listo.

        Returns:
            TradingBot inicializado y conectado.

        Raises:
            SystemExit: Si las credenciales son inválidas o la conexión falla.
        """
        print("  Conectando con Alpaca API...")
        try:
            config = get_config()
            trading_client, data_client = get_clients(config)
        except (ValueError, ConnectionError) as e:
            print(f"\n  ✗ ERROR de conexión: {e}")
            sys.exit(1)

        print("  ✓ Conexión establecida.\n")
        print_account_summary(trading_client)

        if os.getenv("ANTHROPIC_API_KEY", "").strip():
            print("  🧠 Módulo 5 (Sentimiento) ACTIVO — usando Claude Haiku\n")
        else:
            print("  ℹ️  Módulo 5 (Sentimiento) inactivo — configura ANTHROPIC_API_KEY para activarlo\n")

        bot = cls(config, trading_client, data_client)
        notify_startup(config.mode, bot._universo)
        return bot

    # ─── Ciclo de monitoreo (SL/TP cada 30 minutos) ──────────────────────────

    def ciclo_monitoreo(self) -> None:
        """Verifica SL/TP de posiciones abiertas sin hacer análisis nuevo.

        Se ejecuta cada 30 minutos durante el horario de mercado. No actúa
        si no hay posiciones abiertas o el mercado está cerrado.
        """
        posiciones = get_posiciones_abiertas()
        if not posiciones:
            return

        now_et = datetime.now(self.settings.timezone).strftime("%H:%M ET")
        print(f"\n  🔍 [{now_et}] Monitoreo de {len(posiciones)} posición(es):")

        try:
            if not is_market_open(self.trading_client):
                print("  💤 Mercado cerrado.\n")
                return

            precios = self._obtener_precios_actuales(posiciones)
            monitorear_sl_tp(self.trading_client, precios)

        except Exception as e:
            print(f"  ✗ Error en monitoreo: {e}")

    # ─── Ciclo de análisis completo (2 veces al día) ─────────────────────────

    def ciclo_analisis(self, momento: str) -> None:
        """Ciclo completo: datos → indicadores → sentimiento → ejecución.

        Se ejecuta a las 9:35am y 12:30pm ET. Incluye monitoreo previo de
        SL/TP antes de buscar nuevas entradas.

        Args:
            momento: Etiqueta del ciclo ("apertura" o "mediodía") para el log.
        """
        now_et = datetime.now(self.settings.timezone).strftime("%H:%M ET")
        print(f"\n{'='*52}")
        print(f"  ⏱  Ciclo de análisis — {momento.upper()} ({now_et})")
        print(f"{'='*52}")

        try:
            if not is_market_open(self.trading_client):
                print("  💤 Mercado cerrado — ciclo omitido.\n")
                return

            notify_cycle(momento)

            saldo = get_available_cash(self.trading_client)
            print(f"  💰 Saldo disponible (T+1): ${saldo:,.2f}")

            self._monitorear_posiciones_previo()

            # Actualizar universo una vez por día (en el ciclo de apertura)
            if momento == "apertura":
                self._actualizar_universo()

            print(f"\n  📊 Análisis de {len(self._universo)} símbolos (velas 15 min):")
            for symbol in self._universo:
                self._analizar_simbolo(symbol, saldo)

            print(f"\n  ✓ Ciclo {momento} completado.\n")

        except Exception as e:
            print(f"  ✗ Error en ciclo de análisis: {e}")
            notify_error(f"ciclo {momento}", str(e))

    # ─── Tick principal (cada minuto) ────────────────────────────────────────

    def tick(self) -> None:
        """Decide qué acción tomar según la hora ET actual.

        Usa un registro diario para garantizar que cada ciclo de análisis
        corre exactamente una vez por día, aunque el proceso haga varios
        ticks en el mismo minuto (deduplicación por clave fecha+momento).
        """
        now_et = datetime.now(self.settings.timezone)
        hoy    = now_et.date()
        hora   = now_et.hour
        minuto = now_et.minute

        self._resetear_registro_si_nuevo_dia(hoy)

        for slot in self.settings.analysis_slots:
            if (hora, minuto) != (slot.hour, slot.minute):
                continue
            clave = f"{hoy}_{slot.name}"
            if clave in self._ejecutados_hoy:
                return
            self._ejecutados_hoy.add(clave)
            self.ciclo_analisis(slot.name)
            return

        if minuto in (0, 30):
            clave_monitor = f"{hoy}_{hora}_{minuto}_monitor"
            if clave_monitor not in self._ejecutados_hoy:
                self._ejecutados_hoy.add(clave_monitor)
                self.ciclo_monitoreo()

    # ─── Bucle principal ─────────────────────────────────────────────────────

    def run(self) -> None:
        """Lanza el scheduler y entra en el bucle principal (bloqueante).

        Imprime el resumen de configuración, ejecuta un monitoreo inicial
        y luego procesa un tick por minuto indefinidamente.
        """
        self._imprimir_configuracion()
        self.ciclo_monitoreo()

        schedule.every(1).minutes.do(self.tick)
        print("  🕐 Scheduler activo. Ctrl+C para detener.\n")

        while True:
            schedule.run_pending()
            time.sleep(30)

    # ─── Helpers privados ─────────────────────────────────────────────────────

    def _actualizar_universo(self) -> None:
        """Descubre las mejores acciones del día usando el módulo de universo.

        Llama a build_daily_universe que: filtra ~50 acciones por momentum
        técnico y pide a Claude que elija las mejores según noticias del día.
        Actualiza self._universo para que el ciclo de análisis las use.
        """
        try:
            nuevo = build_daily_universe(
                data_client=self.data_client,
                alpaca_api_key=self.config.api_key,
                alpaca_secret_key=self.config.secret_key,
            )
            if nuevo:
                self._universo = nuevo
        except Exception as e:
            print(f"  ⚠️  Error actualizando universo: {e} — se mantiene lista anterior.")

    def _obtener_precios_actuales(self, posiciones: dict) -> dict[str, float]:
        """Consulta el precio actual de cada símbolo con posición abierta."""
        precios: dict[str, float] = {}
        for symbol in posiciones:
            bar = get_latest_bar(self.data_client, symbol)
            if bar is not None:
                precios[symbol] = float(bar["close"])
        return precios

    def _monitorear_posiciones_previo(self) -> None:
        """Revisa SL/TP antes del ciclo de análisis para actuar sobre posiciones abiertas."""
        posiciones = get_posiciones_abiertas()
        if not posiciones:
            return
        print(f"  🔍 Revisando {len(posiciones)} posición(es) abierta(s):")
        precios = self._obtener_precios_actuales(posiciones)
        monitorear_sl_tp(self.trading_client, precios)

    def _analizar_simbolo(self, symbol: str, saldo: float) -> None:
        """Ejecuta el pipeline completo de análisis para un símbolo.

        Pipeline: datos históricos → indicadores → señal técnica →
                  sentimiento (si BUY) → ejecución.

        Args:
            symbol: Ticker del activo.
            saldo:  Saldo disponible para calcular el notional.
        """
        df = get_historical_bars(
            client=self.data_client,
            symbol=symbol,
            timeframe=self.settings.timeframe,
            days_back=self.settings.days_back,
        )
        if df.empty:
            print(f"  🟡 [{symbol}] Sin datos disponibles.")
            return

        print_latest_bar(symbol, df.iloc[-1])

        df_ind = calculate_indicators(df)
        result = get_signal(df_ind, symbol=symbol)
        print_analysis(result)

        senal_final = self._aplicar_filtro_sentimiento(symbol, result.signal)

        ejecutar_senal(
            trading_client=self.trading_client,
            symbol=symbol,
            signal=senal_final,
            precio_actual=result.close,
            saldo_disponible=saldo,
        )

    def _aplicar_filtro_sentimiento(self, symbol: str, signal: Signal) -> Signal:
        """Consulta el sentimiento de noticias y bloquea BUYs negativos.

        Solo se activa cuando la señal técnica es BUY; no afecta SELL ni HOLD.

        Args:
            symbol: Ticker del activo.
            signal: Señal técnica del Módulo 3.

        Returns:
            La señal original, o HOLD si el sentimiento es negativo.
        """
        if signal != Signal.BUY:
            return signal

        sentiment = get_sentiment(
            symbol=symbol,
            alpaca_api_key=self.config.api_key,
            alpaca_secret_key=self.config.secret_key,
        )
        print_sentiment(sentiment)

        if sentiment.available and sentiment.score < 0:
            print(f"  ⚠️  [{symbol}] BUY bloqueado por sentimiento negativo.")
            return Signal.HOLD

        return signal

    def _resetear_registro_si_nuevo_dia(self, hoy: date) -> None:
        """Limpia el registro de ciclos ejecutados al cambiar de día."""
        if self._dia_actual != hoy:
            self._dia_actual = hoy
            self._ejecutados_hoy.clear()

    def _imprimir_configuracion(self) -> None:
        """Muestra el resumen de configuración al arrancar el bot."""
        now_et = datetime.now(self.settings.timezone)
        apertura = self.settings.analysis_slots[0]
        mediodia = self.settings.analysis_slots[1]
        apertura_str = f"{apertura.hour:02d}:{apertura.minute:02d} ET"
        mediodia_str = f"{mediodia.hour:02d}:{mediodia.minute:02d} ET"

        print(f"  📅 Hora actual         : {now_et.strftime('%Y-%m-%d %H:%M ET')}")
        print(f"  🔔 Análisis apertura   : {apertura_str}")
        print(f"  🔔 Análisis mediodía   : {mediodia_str}")
        print(f"  🔄 Monitoreo SL/TP     : cada 30 minutos")
        print(f"  📊 Temporalidad velas  : 15 minutos")
        print(f"  🌐 Universo base       : {', '.join(self.settings.symbols)}")
        print(f"  🔬 Universo dinámico   : se actualiza cada mañana (~50 acciones → top 10)")
        print(f"  🏦 Modo               : {self.config.mode.upper()}\n")


# ─── Punto de entrada ─────────────────────────────────────────────────────────

def main() -> None:
    """Inicializa y arranca el bot de trading."""
    print("\n🤖 Iniciando Auto DayTrading Bot...")
    bot = TradingBot.create()
    bot.run()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        notify_shutdown()
        print("\n\n  🛑 Bot detenido manualmente.\n")
        sys.exit(0)

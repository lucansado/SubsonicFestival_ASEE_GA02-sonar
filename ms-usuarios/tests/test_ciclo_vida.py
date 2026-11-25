import asyncio
from unittest.mock import Mock
import pytest
import main


@pytest.mark.parametrize("fallo", [False, True])
def test_migra_antes_de_consumir_y_detiene_incluso_si_falla(monkeypatch, fallo):
    orden = []
    hilo = Mock()
    monkeypatch.setattr(main, "crear_tablas", lambda: orden.append("migrar"))
    monkeypatch.setattr(main, "inicializar", lambda: orden.append("firebase"))
    consumidor = Mock()
    consumidor.iniciar.side_effect = lambda: orden.append("iniciar") or hilo
    consumidor.detener.side_effect = lambda: orden.append("detener")
    monkeypatch.setattr(main, "consumidor", consumidor)

    async def ejecutar():
        async with main.lifespan(main.app):
            assert orden == ["migrar", "firebase", "iniciar"]
            if fallo:
                raise RuntimeError("fallo durante el servicio")

    if fallo:
        with pytest.raises(RuntimeError):
            asyncio.run(ejecutar())
    else:
        asyncio.run(ejecutar())
    assert orden[-1] == "detener"
    hilo.join.assert_called_once_with(timeout=10)

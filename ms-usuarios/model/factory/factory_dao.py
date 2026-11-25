# ms-usuarios/model/factory/factory_dao.py
from model.dao.entrada_dao import EntradaDAO
from model.dao.usuario_dao import UsuarioDAO


class DAOFactory:
    @staticmethod
    def get_usuario_dao() -> UsuarioDAO:
        return UsuarioDAO()

    @staticmethod
    def get_entrada_dao() -> EntradaDAO:
        return EntradaDAO()

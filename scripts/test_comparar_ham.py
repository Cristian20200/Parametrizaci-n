#!/usr/bin/env python3
"""Pruebas internas con datos sintéticos; no usa registros reales de pacientes."""
import unittest
from decimal import Decimal
from comparar_ham import compare, amount, key

def row(n,code,desc,tariff):
    return {"row":n,"code":code,"desc":desc,"tariff":str(tariff),
            "norm":__import__("homologar").normalize(desc),"money":amount(tariff)}

class ContratoHamTests(unittest.TestCase):
    def test_coincidencia_exacta(self):
        result=compare([row(2,"997104","TOPICACION DE FLUOR EN SOLUCION",25400)],
                       [row(2,"997104","TOPICACIÓN DE FLÚOR EN SOLUCIÓN","25.400")],{})
        self.assertEqual(len(result),1)
        self.assertEqual(result[0]["decision"],"COINCIDENCIA EXACTA")
        self.assertEqual(result[0]["accion_ham"],"MANTENER")

    def test_codigo_propio_misma_descripcion_tarifa(self):
        r=compare([row(2,"OD-009","TOPICACION DE FLUOR EN SOLUCION",25400)],
                  [row(3,"997104","TOPICACION DE FLUOR EN SOLUCION",25400)],{})
        self.assertEqual(r[0]["decision"],"CODIGO PROPIO / EQUIVALENCIA POR VALIDAR")

    def test_tarifa_diferente(self):
        r=compare([row(2,"997104","TOPICACION DE FLUOR EN SOLUCION",25400)],
                  [row(3,"997104","TOPICACION DE FLUOR EN SOLUCION",30000)],{})
        self.assertEqual(r[0]["decision"],"REVISAR DIFERENCIAS")

    def test_ham_fuera_del_anexo(self):
        r=compare([row(2,"997104","TOPICACION DE FLUOR EN SOLUCION",25400)],
                  [row(3,"997104","TOPICACION DE FLUOR EN SOLUCION",25400),
                   row(4,"998001","OTRO PROCEDIMIENTO",20000)],{})
        self.assertEqual(r[-1]["accion_ham"],"EVALUAR INACTIVACION")

    def test_codigo_repetido_diferentes_descripciones(self):
        r=compare([row(2,"123456","PROCEDIMIENTO A",25000),
                   row(3,"123456","PROCEDIMIENTO B",35000)],
                  [row(4,"123456","PROCEDIMIENTO A",25000)],{})
        self.assertTrue(any(x["decision"]=="MISMO CODIGO / DESCRIPCIONES DIFERENTES" for x in r))
        self.assertFalse(any(x["decision"]=="COINCIDENCIA EXACTA" for x in r if x["origen"]=="ANEXO"))

    def test_decimal_colombiano(self):
        self.assertEqual(amount("25.400"),Decimal("25400"))
        self.assertEqual(amount("25.400,50"),Decimal("25400.50"))

if __name__=="__main__":
    unittest.main()

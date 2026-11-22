#!/usr/bin/env python3
"""Pruebas internas con datos sintéticos; no usa registros reales de pacientes."""
import unittest
from decimal import Decimal
from comparar_ham import compare, amount, key, clinical_text, clinical_conflict, clinical_score

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
        self.assertEqual(r[0]["decision"],"EQUIVALENCIA PROPUESTA POR DESCRIPCION Y TARIFA")

    def test_tarifa_diferente(self):
        r=compare([row(2,"997104","TOPICACION DE FLUOR EN SOLUCION",25400)],
                  [row(3,"997104","TOPICACION DE FLUOR EN SOLUCION",30000)],{})
        self.assertEqual(r[0]["decision"],"DIFERENCIA TARIFARIA O DESCRIPTIVA")

    def test_ham_fuera_del_anexo(self):
        r=compare([row(2,"997104","TOPICACION DE FLUOR EN SOLUCION",25400)],
                  [row(3,"997104","TOPICACION DE FLUOR EN SOLUCION",25400),
                   row(4,"998001","OTRO PROCEDIMIENTO",20000)],{})
        self.assertEqual(r[-1]["accion_ham"],"EVALUAR INACTIVACION")

    def test_codigo_repetido_diferentes_descripciones(self):
        r=compare([row(2,"123456","PROCEDIMIENTO A",25000),
                   row(3,"123456","PROCEDIMIENTO B",35000)],
                  [row(4,"123456","PROCEDIMIENTO A",25000)],{})
        self.assertTrue(any(x["decision"]=="MISMO CODIGO CON VARIANTES" for x in r))
        self.assertFalse(any(x["decision"]=="COINCIDENCIA EXACTA" for x in r if x["origen"]=="ANEXO"))


    def test_similitud_por_abreviatura(self):
        a=row(2,"A1","MEDICAMENTO INY 10MG/1ML",25000)
        b=row(3,"B1","MEDICAMENTO INYECTABLE 10MG/1ML",25000)
        self.assertGreaterEqual(clinical_score(a,b),85)
        self.assertFalse(clinical_conflict(a,b))

    def test_diferente_concentracion_no_equivale(self):
        a=row(2,"A1","MEDICAMENTO INY 10MG/1ML",25000)
        b=row(3,"A1","MEDICAMENTO INYECTABLE 20MG/1ML",25000)
        self.assertEqual(clinical_conflict(a,b),"CONCENTRACION DIFERENTE")
        r=compare([a],[b],{})
        self.assertEqual(r[0]["decision"],"CONFLICTO TECNICO")

    def test_similitud_igual_tarifa_codigo_diferente(self):
        r=compare([row(2,"PREST-11","RADIOGRAFIA DE CRANEO SIMPLE",34774)],
                  [row(3,"870001","RX DE CRANEO SIMPLE",34774)],{})
        self.assertEqual(r[0]["origen"],"ANEXO")
        self.assertEqual(r[0]["fila_ham"],3)
        self.assertNotEqual(r[0]["decision"],"EN ANEXO SIN VINCULO CONFIRMADO")

    def test_tarifa_identica_codigo_igual_descripcion_parcial(self):
        r=compare([row(2,"881202","ECOCARDIOGRAMA TRANSTORACICO",268086)],
                  [row(3,"881202","ECOCARDIOGRAMA TRANSTORACICO ADULTO",268086)],{})
        self.assertEqual(r[0]["fila_ham"],3)
        self.assertNotEqual(r[0]["accion_ham"],"EVALUAR CREACION")

    def test_conservar_identificador_subcodigo(self):
        r=compare([row(2,"997106-2","TOPICACION FLUOR EN BARNIZ SERIADA NINOS",25400)],
                  [row(3,"997106-2","TOPICACION FLUOR EN BARNIZ SERIADA NINOS",25400)],{})
        self.assertEqual(r[0]["codigo_ham"],"997106-2")

    def test_misma_fila_ham_no_se_asigna_dos_veces(self):
        a=[row(2,"A-1","PROCEDIMIENTO PRUEBA",50000),
           row(3,"A-2","PROCEDIMIENTO PRUEBA",50000)]
        h=[row(5,"X","PROCEDIMIENTO PRUEBA",50000)]
        r=compare(a,h,{})
        self.assertEqual(sum(bool(x["fila_ham"]) for x in r if x["origen"]=="ANEXO"),1)


    def test_equivalencia_concentraciones(self):
        a=row(2,"10207","ONDANSETRON 8 MG/4ML AMPOLLA",29500)
        b=row(3,"20095751-4","ONDANSETRON 2MG/ML SLN INY AMP X 4ML",29500)
        self.assertEqual(__import__("comparar_ham").concentration(a["desc"]),
                         __import__("comparar_ham").concentration(b["desc"]))
        self.assertEqual(clinical_conflict(a,b),"")
        result=compare([a],[b],{})
        self.assertEqual(result[0]["fila_ham"],3)

    def test_concentracion_distinta_bloquea_homologacion(self):
        a=row(2,"A","ONDANSETRON 8MG/4ML AMPOLLA",29500)
        b=row(3,"B","ONDANSETRON 4MG/4ML AMPOLLA",29500)
        self.assertEqual(clinical_conflict(a,b),"CONCENTRACION DIFERENTE")
        r=compare([a],[b],{})
        self.assertFalse(r[0]["decision"]=="COINCIDENCIA EXACTA")

    def test_dosificacion_multiplicativa_no_es_division(self):
        a=row(2,"A","FARMACO 10MG/1ML",1200)
        b=row(3,"B","FARMACO 10MG X 1ML",1200)
        self.assertNotEqual(__import__("comparar_ham").concentration(a["desc"]),
                            __import__("comparar_ham").concentration(b["desc"]))

    def test_decimal_colombiano(self):
        self.assertEqual(amount("25.400"),Decimal("25400"))
        self.assertEqual(amount("25.400,50"),Decimal("25400.50"))

if __name__=="__main__":
    unittest.main()

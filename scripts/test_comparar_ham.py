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


    def test_adenosina_presentacion_abreviada(self):
        a=row(2,"60940","ADENOSINA 6 MG/2ML AMPOLLA",66226)
        b=row(3,"20139028-2","ADENOSINA 6 MG SLN INY AMP X 2 ML",66226)
        r=compare([a],[b],{})
        self.assertEqual(r[0]["fila_ham"],3)
        self.assertEqual(r[0]["decision"],"EQUIVALENCIA PROPUESTA POR DESCRIPCION Y TARIFA")

    def test_presentation_volume_difference(self):
        a=row(2,"A","ONDANSETRON 2MG/ML AMP X 4ML",1000)
        b=row(3,"B","ONDANSETRON 2MG/ML AMP X 2ML",1000)
        self.assertEqual(clinical_conflict(a,b),"PRESENTACION VOLUMEN DIFERENTE")

    def test_losartan_monoterapia_vs_combinado(self):
        a=row(2,"RX1","LOSARTAN 100 MG TABLETA",4500)
        b=row(3,"RX2","LOSARTAN + HIDROCLOROTIAZIDA 100 + 25 MG TABLETA",4500)
        self.assertEqual(clinical_conflict(a,b),"PRINCIPIOS ACTIVOS O FORMULACION DIFERENTES")
        r=compare([a],[b],{})
        self.assertEqual(r[0]["accion_ham"],"EVALUAR CREACION")
        self.assertEqual(r[-1]["accion_ham"],"EVALUAR INACTIVACION")

    def test_crema_vs_jalea(self):
        a=row(2,"P1","LIDOCAINA 4% JALEA",10000)
        b=row(3,"P2","LIDOCAINA 4% CREMA",10000)
        self.assertEqual(clinical_conflict(a,b),"FORMA FARMACEUTICA DIFERENTE")


    def test_reverse_ham_hidrocortisona_solo_candidato(self):
        a=row(2,"101","HIDROCORTISONA 100 MG AMPOLLA",17866)
        b=row(3,"19926707-1","HIDROCORTISONA 100 MG PPR SLN INY X VIAL",17866)
        r=compare([a],[b],{})
        self.assertTrue(any(x["codigo_ham"]=="19926707-1" for x in r))
        self.assertFalse(any(x["decision"]=="COINCIDENCIA EXACTA" for x in r))

    def test_reverse_ham_no_emparejar_insulina_con_folico(self):
        a=row(2,"701","ACIDO FOLICO 5MG TABLETA",528)
        b=row(3,"27190-3","INSULINA HUMANA ISOFANA NPH 100UI/ML SLN INY VIAL X 10ML",528)
        r=compare([a],[b],{})
        self.assertFalse(any(x["decision"]=="HAM CANDIDATO ANEXO POR VERIFICAR" for x in r))

    def test_alias_metotrexato_metotrexate(self):
        self.assertEqual(clinical_text("METOTREXATE 500 MG/5ML"),
                         clinical_text("METOTREXATO 500MG/5ML"))

    def test_trimebutina_concentracion_equivalente(self):
        from comparar_ham import concentration
        self.assertEqual(concentration("TRIMEBUTINA 10MG/ML"),concentration("TRIMEBUTINA 50MG/5ML"))

    def test_fenoterol_ipratropio_volumen_distinto(self):
        a=row(2,"101","FENOTEROL IPRATROPIO SLN INH FCO X 10ML",64300)
        b=row(3,"202","BROMURO IPRATROPIO/FENOTEROL SOL NEBULIZAR FRA 20ML",64300)
        self.assertEqual(clinical_conflict(a,b),"PRESENTACION VOLUMEN DIFERENTE")

    def test_vigencia_maestro_no_avalada_por_estado_local(self):
        from homologar import master_validity
        self.assertEqual(master_validity({"ESTADO":"ACTIVO"}),
                         "VIGENCIA OFICIAL NO VERIFICADA")
        self.assertEqual(master_validity({"ESTADO":"VIGENTE"}),
                         "VIGENCIA OFICIAL NO VERIFICADA")
        self.assertEqual(master_validity({"ESTADO":"NO VIGENTE"}),
                         "NO VIGENTE SEGUN MAESTRO")
        self.assertEqual(master_validity({"ESTADO":"INACTIVO"}),
                         "NO VIGENTE SEGUN MAESTRO")
        self.assertEqual(master_validity({}),
                         "VIGENCIA OFICIAL NO VERIFICADA")

    def test_decimal_colombiano(self):
        self.assertEqual(amount("25.400"),Decimal("25400"))
        self.assertEqual(amount("25.400,50"),Decimal("25400.50"))

if __name__=="__main__":
    unittest.main()

###############
# DEPENDENCIAS

# tkinter para interfaz gráfica
from ensurepip import version
import tkinter
from tkinter import ttk
import tkinter.simpledialog
from tkinter.filedialog import askdirectory
import inspect

# os para manipular archivos
import os
import datetime

# pandas para tablas
import pandas as pd

# geopandas y shapely para tablas con datos geográficos
import geopandas as gpd
from shapely.geometry import Point, LineString, Polygon
from shapely.wkt import loads

# matplotlib para graficar
import matplotlib.pyplot as plt
# usar un 'backend' apropiado para crear el mapa en formato png 
import matplotlib
matplotlib.use('Agg')

# pillow para imágenes
from PIL import ImageTk,Image

# para procesar archivos kmz
from zipfile import ZipFile
from lxml import html

# para leer datos exif
import exif

# para buscar los nombres de las ciudades por coordenadas
import reverse_geocoder

# para abrir y mostrar mosaicos geotiff
from osgeo import gdal
import numpy as np

# para abrir carpetas de archivos
import webbrowser


###################

global version_bitacora
version_bitacora = 0.6

###################


class Vuelo:

    def __init__(self, carpeta=os.getcwd(), leer_bitacora=False, nombre='', descripcion='', idioma='es') -> None:
        
        self.carpeta       =  carpeta
        self.bitacora_csv  = 'bitacora.csv'
        self.bitacora_kml  = 'bitacora.kml'
        self.bitacora_png  = 'bitacora.png'
        global version_bitacora

        # leer nombres de variables
        ruta_programa = inspect.getframeinfo(inspect.currentframe()).filename
        carpeta_programa = os.path.dirname(os.path.abspath(ruta_programa))
        ruta_archivo_variables = os.path.join(carpeta_programa, '_configuracion', 'variables.xlsx')
        self.tabla_variables = pd.read_excel(ruta_archivo_variables, engine='openpyxl')

        if leer_bitacora:
            # si ya hay una tabla de datos, leerla
            if os.path.exists(os.path.join(carpeta, self.bitacora_csv)):
                self.leer_datos_csv()
            else: 
                leer_bitacora = False
            # si ya hay una imagen del mapa, leerla
            if os.path.exists(os.path.join(carpeta, self.bitacora_png)):
                self.mapa = Image.open(os.path.join(carpeta, self.bitacora_png))

        if not leer_bitacora:
            # crear una tabla de datos vacía
            lista_variables = self.tabla_variables['variable'].tolist()
            self.info = dict.fromkeys(lista_variables)
            self.info['carpeta'] = carpeta
            self.info['nombre'] = nombre
            self.info['descripcion'] = descripcion
            self.info['idioma'] = idioma
            self.info['version_bitacora'] = version_bitacora

        # crear listado de elementos del proyecto (por el momento no está implementado importar desde el kml)
        # crear tabla vacía
        self.elementos = gpd.GeoDataFrame(columns = [
        'archivo', 'descripcion', 'subcarpeta', 'tipo_archivo', 'tamanio',
        'fecha', 'hora', 'datetime', 
        'latitud', 'longitud', 'altitud', 'geometry',
        ], geometry='geometry', crs = 'WGS 84')



    def leer_datos_csv(self) -> None:
        # leer datos de bitacora.csv
        ruta_csv = os.path.join(self.carpeta, self.bitacora_csv)
        datos_archivo = pd.read_csv(ruta_csv, header=None)

        # armar diccionario con los datos del archivo
        lista_variables = self.tabla_variables['variable'].tolist()
        self.info = dict.fromkeys(lista_variables)
        for i, row in datos_archivo.iterrows():
            # columna 0: id - columna 1: nombre de la variable - columna 2: valor
            id = row[0]
            variable = self.tabla_variables.loc[self.tabla_variables['id']==id, 'variable'].values[0]
            valor = row[2]
            if pd.isna(valor):
                valor = ''
            self.info[variable] = valor


    def importar(self, ruta_archivo, reemplazar=False) -> bool:
        '''
        Importa un archivo e incorpora los datos a la tabla de archivos

        Parameters
        ----------
        ruta_archivo : str or list of str
            Ruta completa del archivo, carpeta o lista de múltiples archivos que se quieren importar
        reemplazar : bool, default=False
            Define si se reemplazan los datos existentes si ya existe en la tabla de archivos un archivo con el mismo nombre

        Returns
        -------
        resultado
            True si se pudo importar el archivo, False si no
        '''

        # chequear si se quiere importar una carpeta completa
        if os.path.isdir(ruta_archivo):
            carpeta = ruta_archivo
            # convertir la carpeta en una lista de archivos individuales
            ruta_archivo = sorted([os.path.join(carpeta, file) for file in os.listdir(carpeta)])
            # llamar nuevamente a esta función para cada uno de ellos
            resultado = False
            for ruta_archivo_individual in ruta_archivo:
                resultado_parcial = self.importar(ruta_archivo_individual, reemplazar=reemplazar)
                resultado = resultado or resultado_parcial
            return resultado

        # chequear si el archivo que se quiere importar existe
        if os.path.isfile(ruta_archivo):
            # datos básicos del archivo
            subcarpeta, archivo = os.path.split(ruta_archivo)
            subcarpeta = os.path.relpath(subcarpeta, self.carpeta)
            tamanio = os.path.getsize(ruta_archivo)
            datetime_archivo = pd.to_datetime(datetime.datetime.fromtimestamp(os.path.getmtime(ruta_archivo)))
            fecha = datetime_archivo.strftime('%Y-%m-%d')
            hora = datetime_archivo.strftime('%H:%M:%S')

            # chequear si el archivo a importar se corresponde con alguna de las extensiones de los tipo de archivo listados
            extensiones = {
                'imagen':        ['.jpg', '.jpeg'],
                'telemetría':    ['.tlog'],
                'polígono':      ['.poly'],
                'plan de vuelo': ['.waypoints', '.grid'],
                'mosaico / dem': ['.tif', '.tiff']
            } 
            tipo_archivo = ''
            for posible_tipo_archivo in reversed(list(extensiones.keys())):
                for extension in extensiones[posible_tipo_archivo]:
                    if archivo.lower().endswith(extension):
                        tipo_archivo = posible_tipo_archivo
            # si el archivo no es de ninguno de los tipos listados, no importarlo
            if tipo_archivo == '':
                return False

            # chequear si ya existe un archivo igual en la tabla de archivos del proyecto, para reemplazarlo
            archivos_iguales = self.elementos.loc[(self.elementos.archivo == archivo) & (self.elementos.subcarpeta == subcarpeta)]
            if len(archivos_iguales)>0:
                if reemplazar:
                    fila = archivos_iguales.index.values[0]
                else:
                    return False
            else:
                fila = len(self.elementos)

            # llenar la fila de la tabla con valores 'NA'
            fila_vacia = pd.Series(pd.NA * len(self.elementos.columns), index=self.elementos.columns)
            self.elementos.loc[fila] = fila_vacia
            
            # incorporar los datos básicos
            self.elementos.loc[fila, 'archivo'] = archivo
            self.elementos.loc[fila, 'subcarpeta'] = subcarpeta
            self.elementos.loc[fila, 'tipo_archivo'] = tipo_archivo
            self.elementos.loc[fila, 'tamanio'] = tamanio
            self.elementos.loc[fila, 'fecha'] = fecha
            self.elementos.loc[fila, 'hora'] = hora
            self.elementos.loc[fila, 'datetime'] = datetime_archivo

            # incorporar coordenadas y modificar fecha y hora, según el tipo de archivo

            if tipo_archivo == 'imagen':
                self.fila_datos_imagen(fila)
            if tipo_archivo == 'telemetría':
                self.fila_datos_telemetria(fila)
            if tipo_archivo == 'plan de vuelo':
                self.fila_datos_plan_de_vuelo(fila)
            if tipo_archivo == 'polígono':
                self.fila_datos_poligono(fila)
            #if tipo_archivo == 'mosaico / dem':

            print('Se agregó el archivo ' + archivo + ' - Tipo de archivo: ' + tipo_archivo)
            return True

        else:
            # si el archivo no existe
            return False



    def fila_datos_imagen(self, fila_elemento): 
        archivo = self.elementos.loc[fila_elemento, 'archivo']
        subcarpeta = self.elementos.loc[fila_elemento, 'subcarpeta']
        ruta_archivo = os.path.join(self.carpeta, subcarpeta, archivo)
        # leer datos EXIF
        with open(ruta_archivo, "rb") as datos_imagen:
            imagen = exif.Image(datos_imagen)
        # obtener fecha y hora de captura de la imagen
        if imagen.has_exif:
            datetime_original = imagen.get('datetime_original', pd.NA)
            if pd.notna(datetime_original):
                fecha, hora = datetime_original.split()
                fecha = fecha.replace(':','-')
                datetime_archivo = pd.to_datetime(fecha + ' ' + hora)
                # incorporar los datos a la tabla
                self.elementos.loc[fila_elemento, 'fecha'] = fecha
                self.elementos.loc[fila_elemento, 'hora'] = hora
                self.elementos.loc[fila_elemento, 'datetime'] = datetime_archivo
            # obtener datos de la cámara
            marca = imagen.get('make', pd.NA)
            modelo = imagen.get('model', pd.NA)
            if pd.notna(marca) & pd.notna(modelo):
                if modelo.startswith(marca): camara = modelo
                else: camara = marca + ' - ' + modelo
            else:
                if pd.notna(marca): camara = marca
                elif pd.notna(modelo): camara = modelo
                else: camara = pd.NA
            # velocidad de exposición
            exposicion = imagen.get('exposure_time', pd.NA)
            # sensibilidad ISO
            iso_1 = imagen.get('iso_speed_ratings', pd.NA)
            iso_2 = imagen.get('photographic_sensitivity', pd.NA)
            if pd.notna(iso_1): iso = iso_1
            elif pd.notna(iso_2): iso = iso_2
            else: iso = pd.NA
            # incorporar los datos a la tabla
            self.elementos.loc[fila_elemento, 'camara'] = camara
            self.elementos.loc[fila_elemento, 'exposicion'] = exposicion
            self.elementos.loc[fila_elemento, 'iso'] = iso
            
            # obtener coordenadas GPS
            latitud = imagen.get('gps_latitude', pd.NA)
            if pd.notna(latitud):
                latitud = self.coordenadas_decimales(imagen.gps_latitude, imagen.gps_latitude_ref)
                longitud = self.coordenadas_decimales(imagen.gps_longitude, imagen.gps_longitude_ref)
                altitud = imagen.gps_altitude
                geometry = Point(longitud, latitud, altitud)
                # incorporar los datos a la tabla
                self.elementos.loc[fila_elemento, 'latitud'] = latitud
                self.elementos.loc[fila_elemento, 'longitud'] = longitud
                self.elementos.loc[fila_elemento, 'altitud'] = altitud
                self.elementos.loc[fila_elemento, 'geometry'] = geometry

    def coordenadas_decimales(self, coordenadas, coordenadas_ref):
        grados_decimales = coordenadas[0] + \
                        coordenadas[1] / 60 + \
                        coordenadas[2] / 3600
        if coordenadas_ref == "S" or coordenadas_ref == "W":
            grados_decimales = -grados_decimales
        return grados_decimales


    def fila_datos_telemetria(self, fila_elemento):
        archivo = self.elementos.loc[fila_elemento, 'archivo']
        # obtener fecha y hora del nombre de archivo
        fecha = archivo[:10]
        hora = archivo[11:19].replace('-',':')
        datetime_archivo = pd.to_datetime(fecha + ' ' + hora)
        # incorporar los datos a la tabla
        self.elementos.loc[fila_elemento, 'fecha'] = fecha
        self.elementos.loc[fila_elemento, 'hora'] = hora
        self.elementos.loc[fila_elemento, 'datetime'] = datetime_archivo


    def fila_datos_plan_de_vuelo(self, fila_elemento):
        archivo = self.elementos.loc[fila_elemento, 'archivo']
        subcarpeta = self.elementos.loc[fila_elemento, 'subcarpeta']
        ruta_archivo = os.path.join(self.carpeta, subcarpeta, archivo)
        if archivo.endswith('.waypoints'):
            geometry, altitud_inicial, altitud_media, velocidad_de_vuelo = self.leer_plan_de_vuelo(ruta_archivo)
            self.elementos.loc[fila_elemento, 'latitud'] = geometry.centroid.xy[1][0]
            self.elementos.loc[fila_elemento, 'longitud'] = geometry.centroid.xy[0][0]
            self.elementos.loc[fila_elemento, 'altitud'] = altitud_inicial
            self.elementos.loc[fila_elemento, 'geometry'] = geometry



    def leer_plan_de_vuelo(self, ruta_plan_de_vuelo):
        puntos = []
        altitud_inicial = 0
        with open(ruta_plan_de_vuelo) as archivo:
            for linea in archivo:
                if not linea.startswith('QGC'):
                    INDEX, CURRENT_WP, COORD_FRAME, COMMAND, PARAM1, PARAM2, PARAM3, PARAM4, PARAM5_X_LATITUDE, PARAM6_Y_LONGITUDE, PARAM7_Z_ALTITUDE, AUTOCONTINUE = linea.split()
                    
                    if (INDEX=='0') & (COORD_FRAME=='0'):
                        altitud_inicial = float(PARAM7_Z_ALTITUDE)

                    if COMMAND=='178':
                        velocidad = float(PARAM2)

                    if (COMMAND=='16') &(INDEX!='0'):
                        if COORD_FRAME=='0': # altitud absoluta
                            altitud = float(PARAM7_Z_ALTITUDE)
                        if COORD_FRAME=='3': # altitud relativa
                            altitud = float(PARAM7_Z_ALTITUDE) + altitud_inicial                    
                        puntos.append([float(PARAM6_Y_LONGITUDE), float(PARAM5_X_LATITUDE), altitud])

        altitud_media = 0
        for punto in puntos:
            altitud_media += punto[2] / len(puntos)

        recorrido = LineString(puntos) 
        return recorrido, altitud_inicial, altitud_media, velocidad



    def fila_datos_poligono(self, fila_elemento):
        archivo = self.elementos.loc[fila_elemento, 'archivo']
        subcarpeta = self.elementos.loc[fila_elemento, 'subcarpeta']
        ruta_archivo = os.path.join(self.carpeta, subcarpeta, archivo)
        if archivo.endswith('.poly'):
            geometry = self.leer_poligono(ruta_archivo)
            self.elementos.loc[fila_elemento, 'latitud'] = geometry.centroid.xy[1][0]
            self.elementos.loc[fila_elemento, 'longitud'] = geometry.centroid.xy[0][0]
            self.elementos.loc[fila_elemento, 'geometry'] = geometry            

    def leer_poligono(self, ruta_poligono):
        vertices = []
        with open(ruta_poligono) as archivo:
            for linea in archivo:
                if not linea.startswith('#'):
                    latitud, longitud = linea.split(" ")
                    vertices.append([float(longitud), float(latitud)])
        poligono = Polygon(vertices) 
        return poligono



    def actualizar_datos(self):

        nombre = self.info['nombre']
        idioma = self.info['idioma']
        descripcion = self.info['descripcion']
        carpeta = self.info['carpeta']
        global version_bitacora
        fecha = ''
        hora = ''
        superficie_cubierta = ''
        lista_imagenes = ''
        camara = ''
        exposicion = ''
        iso = ''
        latitud = ''
        longitud = ''
        altitud = ''
        altitud_de_vuelo = ''
        velocidad_de_vuelo = ''
 
        # listar poligonos
        poligonos = self.elementos.loc[self.elementos.tipo_archivo == 'polígono']
        if len(poligonos)>1: poligono = ', '.join(poligonos.archivo.to_list())
        elif len(poligonos)==1: poligono = poligonos.archivo.to_list()[0]
        else: poligono = ''
        # tomar las coordenadas del polígono más reciente
        if len(poligonos)>0:
            geometry_poligono = poligonos.sort_values(by='datetime', ascending=False).geometry.to_list()[0]
            latitud = geometry_poligono.centroid.y
            longitud = geometry_poligono.centroid.x

        # listar planes de vuelo
        planes = self.elementos.loc[self.elementos.tipo_archivo == 'plan de vuelo']
        if len(planes)>1: plan_de_vuelo = ', '.join(planes.archivo.to_list())
        elif len(planes)==1: plan_de_vuelo = planes.archivo.to_list()[0]
        else: plan_de_vuelo = ''
        # tomar las coordenadas y datos de vuelo del plan de vuelo más reciente
        if len(planes)>0:
            archivo_plan = planes.sort_values(by='datetime', ascending=False).archivo.to_list()[0]
            subcarpeta_plan = planes.sort_values(by='datetime', ascending=False).subcarpeta.to_list()[0]
            if archivo_plan.endswith('.waypoints'): 
                ruta_archivo = os.path.join(self.carpeta, subcarpeta_plan, archivo_plan)
                geometry, altitud_inicial, altitud_media, velocidad_de_vuelo = self.leer_plan_de_vuelo(ruta_archivo)
                altitud_de_vuelo = altitud_media - altitud_inicial
                altitud = altitud_inicial
                latitud = geometry.centroid.y
                longitud = geometry.centroid.x

        # listar registros de telemetría
        registros = self.elementos.loc[self.elementos.tipo_archivo == 'telemetría']
        if len(registros)>1: registro_telemetria = ', '.join(registros.archivo.to_list())
        elif len(registros)==1: registro_telemetria = registros.archivo.to_list()[0]
        else: registro_telemetria = ''
        # tomar la fecha de la primera telemetría
        if len(registros)>0:
            fecha = registros.sort_values(by='datetime').fecha.to_list()[0]
            hora = registros.sort_values(by='datetime').hora.to_list()[0]

        # imágenes (si hay imágenes georreferenciadas, usar sólo esas)
        imagenes = self.elementos.loc[self.elementos.tipo_archivo=='imagen']
        imagenes_georreferenciadas = imagenes.loc[pd.notna(imagenes.latitud)]
        if len(imagenes_georreferenciadas) > 0:
            imagenes = imagenes_georreferenciadas
        # cantidad de imágenes
        cantidad_de_imagenes = len(imagenes)
        if cantidad_de_imagenes > 0:
            #tomar la fecha y hora de la primera imagen
            fecha = imagenes.sort_values(by='datetime').fecha.values[0]
            hora = imagenes.sort_values(by='datetime').hora.values[0]
            # listar imágenes
            if len(imagenes) > 1:
                lista_imagenes = imagenes.archivo.iloc[0] + ' - ' + imagenes.archivo.iloc[len(imagenes)-1]
            elif len(imagenes) == 1:
                lista_imagenes = imagenes.archivo.iloc[0]
            # datos de la cámara
            camara = imagenes.camara.values[0]
            exposicion = imagenes.exposicion.values[0]
            iso = imagenes.iso.values[0]
            # coordenadas promedio de las imágenes
            latitud = imagenes.latitud.mean()
            longitud = imagenes.longitud.mean()
            altitud = imagenes.altitud.max()
            # superficie cubierta por las imágenes
            coordenadas = imagenes[['longitud', 'latitud']]
            coordenadas = coordenadas.loc[(pd.notna(coordenadas.latitud)) & (pd.notna(coordenadas.longitud))] 
            if len(coordenadas)>0: 
                puntos = gpd.GeoSeries(gpd.tools.collect(gpd.points_from_xy(coordenadas.longitud, coordenadas.latitud, crs = 'WGS 84')), crs = 'WGS 84')
                area_cubierta_escala_metros = puntos.convex_hull.to_crs(3857)
                superficie_cubierta = area_cubierta_escala_metros.area[0]

        # listar mosaicos ordenados por fecha (más reciente primero)
        mosaicos = self.elementos.sort_values(by='datetime', ascending=False).loc[self.elementos.tipo_archivo == 'mosaico / dem']
        # excluir los archivos que sean dsm o dtm
        mosaicos = mosaicos[~mosaicos['archivo'].str.endswith('dsm.tif')]
        mosaicos = mosaicos[~mosaicos['archivo'].str.endswith('dtm.tif')]
        # separar y poner primero en la lista los que terminan en 'orthophoto.tif'
        mosaicos_orthophoto_tif = mosaicos.loc[mosaicos['archivo'].str.endswith('orthophoto.tif')]
        mosaicos_no_orthophoto_tif = mosaicos.loc[~mosaicos['archivo'].str.endswith('orthophoto.tif')]
        mosaicos = pd.concat([mosaicos_orthophoto_tif, mosaicos_no_orthophoto_tif])
        # listar mosaicos
        if len(mosaicos)>1: mosaico = ', '.join(mosaicos.archivo.to_list())
        elif len(mosaicos)==1: mosaico = mosaicos.archivo.to_list()[0]
        else: mosaico = ''

        # listar dems/dtms ordenados por fecha (más reciente primero)
        modelos_de_elevacion = self.elementos.sort_values(by='datetime', ascending=False).loc[self.elementos.tipo_archivo == 'mosaico / dem']
        # dejar sólo los archivos que sean dsm o dtm
        modelos_de_elevacion = mosaicos[(modelos_de_elevacion['archivo'].str.endswith('dsm.tif')) | (modelos_de_elevacion['archivo'].str.endswith('dtm.tif'))]
        # listar dems/dtms
        if len(modelos_de_elevacion)>1: modelo_de_elevacion = ', '.join(modelos_de_elevacion.archivo.to_list())
        elif len(modelos_de_elevacion)==1: modelo_de_elevacion = modelos_de_elevacion.archivo.to_list()[0]
        else: modelo_de_elevacion = ''

        # localidad
        coordenadas = (latitud, longitud)
        localidad = pd.NA
        if pd.notna(latitud) & pd.notna(longitud):
            localidad = reverse_geocoder.search(coordenadas, mode=1)[0]
            pais = localidad['cc']
            prov = localidad['admin1']
            ciudad = localidad['name']
            localidad = ciudad + ', ' + prov + ', ' + pais

        lista_variables = [
        'nombre', 'descripcion', 'localidad',
        'carpeta', 
        'fecha', 'hora', 
        'registro_telemetria', 'poligono', 
        'plan_de_vuelo', 'altitud_de_vuelo', 'velocidad_de_vuelo', 
        'imagenes', 'cantidad_de_imagenes', 'superficie_cubierta',
        'camara', 'iso', 'exposicion', 
        'mosaico', 'modelo_de_elevacion',
        'latitud', 'longitud', 'altitud', 
        'idioma', 'version_bitacora'
        ]
        lista_valores = [
        nombre, descripcion, localidad,
        carpeta, 
        fecha, hora, 
        registro_telemetria, poligono, 
        plan_de_vuelo, altitud_de_vuelo, velocidad_de_vuelo,
        lista_imagenes, cantidad_de_imagenes, superficie_cubierta,
        camara, iso, exposicion, 
        mosaico, modelo_de_elevacion,
        latitud, longitud, altitud, 
        idioma, version_bitacora
        ]

        # guardar datos en la tabla self.info (dict)
        for dato, valor in zip(lista_variables, lista_valores):
            self.info[dato] = valor


    def crear_mapa(self, tamanio=7, mosaico=True, imagenes=True, poligono=True, plan_de_vuelo=True):

        # crear figura
        fig, ax = plt.subplots(1, figsize=(tamanio, tamanio), dpi=200)  # crear imagen al doble de la resolución, para luego reducirla
        ax.set_axis_off()

        if mosaico:

            # listar mosaicos/dems ordenados por fecha (más reciente primero)
            mosaicos = self.elementos.sort_values(by='datetime', ascending=False).loc[self.elementos.tipo_archivo == 'mosaico / dem']
            # separar y poner primero en la lista los que terminan en 'orthophoto.tif', y últimos los dsm/dtm
            mosaicos_orthophoto_tif = mosaicos.loc[mosaicos['archivo'].str.endswith('orthophoto.tif')]
            mosaicos_dsm_tif = mosaicos.loc[mosaicos['archivo'].str.endswith('dsm.tif')]
            mosaicos_dtm_tif = mosaicos.loc[mosaicos['archivo'].str.endswith('dtm.tif')]
            mosaicos_resto = mosaicos.loc[(~mosaicos['archivo'].str.endswith('orthophoto.tif')) & (~mosaicos['archivo'].str.endswith('dsm.tif')) & (~mosaicos['archivo'].str.endswith('dtm.tif'))]
            mosaicos = pd.concat([mosaicos_orthophoto_tif, mosaicos_resto, mosaicos_dsm_tif, mosaicos_dtm_tif])
            if len(mosaicos) > 0:
                archivo_mosaico = mosaicos.archivo.to_list()[0]
                subcarpeta_mosaico = mosaicos.subcarpeta.to_list()[0]
                path = os.path.join(self.carpeta, subcarpeta_mosaico, archivo_mosaico)
                self.agregar_mosaico_al_mapa(ax, path)
            else:
                # si no se encontró un mosaico/dem para mostrar, habilitar a que se muestre la demás información
                mosaico = False
    
            '''
            # elegir el primero de la lista
            archivo_mosaico = self.datos.loc[self.datos.dato=='mosaico', 'valor'].values[0]
            archivo_modelo_de_elevacion = self.datos.loc[self.datos.dato=='modelo_de_elevacion', 'valor'].values[0]
            # si no hay mosaico pero sí hay un dem, se muestra el dem
            if (archivo_mosaico == '') and (archivo_modelo_de_elevacion != ''):
                archivo_mosaico = archivo_modelo_de_elevacion
            # mostrar el mosaico
            if archivo_mosaico!='':
                # si hay un mosaico, se muestra sólo el mosaico
                subcarpeta_mosaico = self.elementos.loc[self.elementos.archivo==archivo_mosaico, 'subcarpeta'].values[0]
                path = os.path.join(self.carpeta, subcarpeta_mosaico, archivo_mosaico)
                self.agregar_mosaico_al_mapa(ax, path)
          
            else:
                # si no se encontró un mosaico para mostrar, habilitar a que se muestre la demás información
                mosaico = False
            '''

        # si no se muestra el mosaico, mostrar polígono, plan de vuelo e imágenes
        if poligono and not mosaico:
            poligonos = self.elementos.loc[self.elementos.tipo_archivo == 'polígono']
            for i, elemento in poligonos.iterrows():
                puntos_poligono = elemento['geometry']
                if pd.notna(puntos_poligono):
                    poligono = gpd.GeoSeries(puntos_poligono, crs = 'WGS 84')
                    poligono.plot(ax=ax, color='#d40000', alpha=0.1, zorder=2)

        if plan_de_vuelo and not mosaico:
            planes = self.elementos.loc[self.elementos.tipo_archivo == 'plan de vuelo']
            for i, elemento in planes.iterrows():
                puntos_plan_de_vuelo = elemento['geometry']
                if pd.notna(puntos_plan_de_vuelo):
                    plan_de_vuelo = gpd.GeoSeries(puntos_plan_de_vuelo, crs = 'WGS 84')
                    plan_de_vuelo.plot(ax=ax, color='#d40000', alpha=0.4, linewidth=tamanio*1, linestyle='dashed', capstyle='round', zorder=3)

        if imagenes and not mosaico:
            imagenes_con_coordenadas = self.elementos.loc[(self.elementos.tipo_archivo=='imagen') & (pd.notna(self.elementos.geometry))]
            if len(imagenes_con_coordenadas) > 0:
                puntos_imagenes = gpd.GeoSeries(gpd.tools.collect(gpd.points_from_xy(imagenes_con_coordenadas.longitud, imagenes_con_coordenadas.latitud, crs = 'WGS 84')), crs = 'WGS 84')
                puntos_imagenes = puntos_imagenes.values
                imagenes = gpd.GeoSeries(puntos_imagenes, crs = 'WGS 84')
                imagenes.plot(ax=ax, color='#5599ff', alpha=0.9, markersize=tamanio*tamanio*2.5, linewidth=0, zorder=5)
                linea_recorrido = LineString(gpd.points_from_xy(imagenes_con_coordenadas.longitud, imagenes_con_coordenadas.latitud, crs = 'WGS 84'))
                recorrido = gpd.GeoSeries(linea_recorrido, crs = 'WGS 84')
                recorrido.plot(ax=ax, color='#5599ff', alpha=0.9, linewidth=tamanio*0.6, linestyle='solid', capstyle='round', zorder=4)
                

        # crear y luego borrar una imagen png temporal del mapa (evita algunos errores de origen desconocido)
        ruta_programa = inspect.getframeinfo(inspect.currentframe()).filename
        carpeta_programa = os.path.dirname(os.path.abspath(ruta_programa))
        ruta_archivo_temporal = os.path.join(carpeta_programa, '_temp.png')
        fig.savefig(ruta_archivo_temporal)
        os.remove(ruta_archivo_temporal)

        # transformar la figura Matplotlib a una imagen Pillow y guardarla
        imagen_mapa = Image.frombytes('RGB', fig.canvas.get_width_height(),fig.canvas.tostring_rgb()).resize((int(tamanio*100),int(tamanio*100)), Image.ANTIALIAS)
        self.mapa = imagen_mapa

    def agregar_mosaico_al_mapa(self, ax, ruta_archivo):
        # leer archivo de mosaico
        datos_mosaico = gdal.Open(ruta_archivo, gdal.GA_ReadOnly)
        # procesar cada banda individual
        bandas_mosaico = datos_mosaico.RasterCount
        for i in range(1, bandas_mosaico+1):
            # leer banda
            banda_mosaico = datos_mosaico.GetRasterBand(i)
            datos_mosaico_banda = banda_mosaico.ReadAsArray()
            # cambiar los valores 'no data' por nan
            ndval = banda_mosaico.GetNoDataValue()
            if ndval!=None:
                datos_mosaico_banda[datos_mosaico_banda==ndval] = np.nan
            # agrupar las bandas en un stack
            if i==1:
                datos_mosaico_stack = datos_mosaico_banda
            else:
                datos_mosaico_stack = np.dstack((datos_mosaico_stack, datos_mosaico_banda))
        # mostrar el mosaico en la figura
        ax.imshow(datos_mosaico_stack, cmap='Greys')



    def guardar_png(self): #, fig):
        #fig.save(os.path.join(self.carpeta, 'bitacora.png'), 'PNG')
        self.mapa.save(os.path.join(self.carpeta, 'bitacora.png'), 'PNG')


    def guardar_csv(self) -> None:
        # ruta donde guardar el archivo
        ruta = os.path.join(self.carpeta, self.bitacora_csv)
        # unir la tabla con los valores y la tabla con los nombres de las variables en los distintos idiomas
        dataframe_info = pd.DataFrame(self.info.items())
        dataframe_info.columns = ['variable', 'valor']
        dataframe_info.set_index('variable', drop=True, inplace=True)
        dataframe_csv = self.tabla_variables.join(dataframe_info, on='variable')
        # elegir el idioma en el que se guardan los nombres de las variables en la tabla
        idioma = self.info['idioma']
        dataframe_csv = dataframe_csv[['id', idioma, 'valor']]
        # guardar la tabla
        dataframe_csv.to_csv(ruta, index=False, header=False)


    def guardar_kml(self) -> None:

            # open a plain text file for output
            nombre_kml = os.path.join(self.carpeta, self.bitacora_kml)
            with open(nombre_kml, 'w') as output:
                    
                    # set up the document header
                    output.write('<?xml version="1.0" encoding="utf-8" ?>\n')
                    output.write('<kml xmlns="http://www.opengis.net/kml/2.2">>\n')
                    output.write('<Document>\n')
                    output.write('<name>' + self.info['nombre'] + '</name>\n\n\n')

                    # tipos de archivo a exportar
                    tipos_archivo = ['plan de vuelo', 'polígono', 'imagen']
                    for tipo_archivo in tipos_archivo:

                        # identificar los elementos que corresponden al tipo de archivo
                        #elementos = self.elementos.loc[self.elementos.tipo_archivo == tipo_archivo]
                        elementos = self.elementos.loc[(self.elementos.tipo_archivo == tipo_archivo) & (pd.notna(self.elementos.geometry))]
                        if tipo_archivo=='imagen':
                            # sólo exportar las imagenes con coordenadas
                            elementos = elementos.loc[pd.notna(elementos.geometry)]

                        if len(elementos) > 0:
                            # crear carpeta
                            output.write('  <Folder><name>' + tipo_archivo + '</name>\n')

                            # exportar cada elemento
                            for i, elemento in elementos.iterrows():
                                # nombre del archivo
                                output.write('    <Placemark>\n')
                                output.write('      <name>' + elemento.archivo + '</name>\n')
                                # datos del archivo
                                if tipo_archivo=='imagen':
                                    lista_variables = ['archivo','subcarpeta','tamanio','fecha','hora','latitud','longitud','altitud','camara','exposicion','iso']
                                else:
                                    lista_variables = ['archivo','subcarpeta','tamanio']
                                output.write('      <ExtendedData>\n')
                                for dato in lista_variables:
                                    output.write('        <Data name="' + dato + '">\n')
                                    output.write('          <value>' + str(elemento[dato]) + '</value>\n')
                                    output.write('        </Data>\n')
                                output.write('      </ExtendedData>\n')
                                # exportar elemento
                                if tipo_archivo=='imagen':
                                    # link para mostrar la imagen al hacer clic
                                    output.write("      <description><![CDATA[<img src='file:///" + os.path.join(self.carpeta, elemento.subcarpeta, elemento.archivo) +"'  width='200' />]]> </description>\n")
                                    # estilo del icono
                                    output.write('      <Style>\n')
                                    output.write('        <IconStyle><Icon><href>http://maps.google.com/mapfiles/kml/shapes/placemark_square.png</href></Icon></IconStyle>\n')    # icono
                                    output.write('        <LabelStyle><scale>0</scale></LabelStyle>\n')   # que no muestre el nombre de todas las imágenes
                                    output.write('      </Style>\n')
                                    # coordenadas de la imagen
                                    output.write('      <Point><coordinates>\n')
                                    output.write('          ' + str(elemento.longitud) + ',' + str(elemento.latitud) + ',' + str(elemento.altitud) + '\n')    # coordenadas
                                    output.write('      </coordinates><altitudeMode>clampToGround</altitudeMode></Point>\n') 
                                if tipo_archivo=='plan de vuelo':
                                    # línea del plan de vuelo
                                    output.write('    <Style><LineStyle><color>cc15f8ff</color><width>8</width></LineStyle></Style>\n')       # color de línea amarillo 80%
                                    output.write('      <MultiGeometry><LineString><coordinates>\n')
                                    puntos = LineString(loads(str(elemento.geometry)))
                                    for x,y in zip(puntos.coords.xy[0], puntos.coords.xy[1]):
                                        output.write('          ' + str(x) + ',' + str(y) + ',0\n')
                                    output.write('      </coordinates></LineString></MultiGeometry>\n')  
                                if tipo_archivo=='polígono':
                                    # área del polígono
                                    output.write('    <Style><PolyStyle><color>330b07e8</color><width>8</width><fill>1</fill><outline>0</outline></PolyStyle></Style>\n')       # color de relleno rojo 20%
                                    output.write('      <MultiGeometry><Polygon><outerBoundaryIs><LinearRing><coordinates>\n')
                                    puntos = Polygon(loads(str(elemento.geometry)))
                                    for x,y in zip(puntos.exterior.coords.xy[0], puntos.exterior.coords.xy[1]):
                                        output.write('          ' + str(x) + ',' + str(y) + ',0\n')
                                    output.write('      </coordinates></LinearRing></outerBoundaryIs></Polygon></MultiGeometry>\n')                                                                                                         
                                
                                # cerrar placemark
                                output.write('    </Placemark>\n')
                            
                            # cerrar carpeta
                            output.write('  </Folder>\n\n\n')

                    # fin del archivo kml
                    output.write('</Document>\n')
                    output.write('</kml>\n')





###################################################################################
#                                INTERFAZ GRÁFICA                                 #
###################################################################################


if __name__ == "__main__":


    #########
    # IDIOMA

    def abrir_traducciones():
        ''' abre el archivo de traducciones
        '''
        global traducciones
        traducciones = pd.read_excel(ruta_archivo_traducciones, engine='openpyxl')
        global lista_idiomas_codigos
        global lista_idiomas_nombres
        lista_idiomas_codigos = traducciones.columns.to_list()
        lista_idiomas_nombres = traducciones.iloc[0, :].to_list()


    def _(texto, idioma_origen='', idioma_destino=''):
        ''' traduce cada uno de los textos de la interfaz
            idioma_origen: idioma de origen, por defecto español
            idioma_destino: idioma de destino, por defecto el seleccionado por el usuario
        '''

        # si no se especifica el idioma de origen, se asume que se trata de los textos en el idioma original del programa
        if idioma_origen=='':
            idioma_origen = idioma_programa
        # si no se especifica el idioma de destino, se asume que se trata del idioma configurado para la interfaz
        if idioma_destino=='':
            idioma_destino = idioma

        # chequear si el texto ya está traducido en el listado
        if texto in traducciones[idioma_origen].to_list():
            posicion = traducciones[idioma_origen].to_list().index(texto)
            traduccion = traducciones.loc[posicion, idioma_destino]
            if traduccion=='' or traducciones.isnull().loc[posicion, idioma_destino]:
                return texto
            else:
                return traduccion
        # si no está traducido, agregarlo al listado para que pueda ser traducido después
        else:
            traducciones.loc[traducciones.index.max() + 1] = ''
            traducciones.loc[traducciones.index.max(), idioma_origen] = texto
            writer = pd.ExcelWriter(ruta_archivo_traducciones, engine='xlsxwriter')
            #traducciones.reset_index(drop=False).to_excel(writer, sheet_name='Traducciones', index=False)
            traducciones.to_excel(writer, sheet_name='Traducciones', index=False)
            writer.save()
            return texto

    def elegir_idioma():
        ''' interfaz para elegir el idioma de la aplicación
        '''

        def funcion_seleccion(evt):
            w = evt.widget
            seleccion = lista_idiomas_codigos[w.curselection()[0]]
            global idioma
            idioma = seleccion
            # cerrar ventana
            ventana_idioma.destroy()

        # usar variable global con el código de idioma actualmente en uso
        global idioma
        global idioma_programa
        global lista_idiomas_codigos
        global lista_idiomas_nombres

        # crear nueva ventana
        ventana_idioma = tkinter.Toplevel(ventana)
        #ventana_idioma.overrideredirect(True)
        ventana_idioma.config(bg='white')
        ventana_idioma.title('Bitácora')
        ventana_idioma.iconphoto(False, tkinter.PhotoImage(file='./_iconos/icono.png'))

        # crear lista para seleccionar el idioma
        scrollbar = tkinter.Scrollbar(ventana_idioma, relief=tkinter.FLAT)
        listado = tkinter.Listbox(
            ventana_idioma, selectmode = 'browse', yscrollcommand = scrollbar.set, 
            relief=tkinter.FLAT)

        # agregar idiomas a la lista
        listado.insert(tkinter.END, *lista_idiomas_nombres)

        # seleccionar el idioma actual
        posicion_idioma_inicial = lista_idiomas_codigos.index(idioma_programa)
        listado.selection_set(posicion_idioma_inicial)
        listado.activate(posicion_idioma_inicial)
        listado.see(posicion_idioma_inicial)
        listado.focus_set()

        # asignar función para cuando se selecciona un idioma
        listado.bind('<<ListboxSelect>>', funcion_seleccion)
        listado.pack()
        ventana_idioma.wait_window() 

   

    ######################
    # VARIABLES DE INICIO

    def leer_variables_inicio():
        global variables_inicio
        global idioma
        global lista_vuelos
        # leer variables de configuración del programa
        variables_inicio = pd.read_csv(ruta_archivo_inicio).set_index('variable')
        idioma = variables_inicio.valor['idioma']
        print(idioma)
        # leer lista de vuelos
        lista_vuelos = pd.read_csv(ruta_archivo_vuelos, index_col=0, dtype=object)
        lista_vuelos = lista_vuelos.fillna('')


    def guardar_variables_inicio():
        global variables_inicio
        global idioma
        global lista_vuelos
        variables_inicio.valor['idioma'] = idioma
        variables_inicio.to_csv(ruta_archivo_inicio)
        lista_vuelos.to_csv(ruta_archivo_vuelos)


    ####################################
    # FUNCIONES DE LA VENTANA PRINCIPAL
    
    def mostrar_lista_vuelos():
        ''' función para actualizar la lista de vuelos en la ventana principal
        '''
        global lista_vuelos
        # limpiar listado
        for i in listado_vuelos.get_children():
            listado_vuelos.delete(i)
        # completar listado
        for i, v in lista_vuelos.iterrows():
            fecha = v.fecha
            hora = v.hora
            nombre = v.nombre
            descripcion = v.descripcion
            listado_vuelos.insert("",'end',text=i+1,values=(fecha, hora, nombre, descripcion))

    def mensaje_de_espera(texto):
        ventana_espera = tkinter.Toplevel(ventana)
        ventana_espera.transient()
        ventana_espera.wm_geometry("200x75")
        ventana_espera.title('')
        ventana_espera.iconphoto(False, tkinter.PhotoImage(file='./_iconos/icono.png'))
        tkinter.Label(ventana_espera, text=texto).pack(expand=True)
        return ventana_espera
        
    def abrir_vuelo(carpeta='', actualizar=False, **kwargs):
        ''' interfaz para abrir un proyecto existente
        '''
        tamanio_mapa = 800  # tamaño en pixels del mapa para guardar en png

        # si no se especifica una carpeta, se pide al usuario
        if carpeta=='': carpeta = askdirectory(title=_('Abrir vuelo'))   # initialdir=...

        # mostrar una ventana con el mensaje de espera
        espera = mensaje_de_espera(_('Leyendo archivos') + '...')
        espera.update()

        if actualizar:
            vuelo = Vuelo(carpeta=carpeta, leer_bitacora=False, **kwargs)
            # importar los archivos contenidos en la carpeta y subcarpetas
            vuelo.importar(carpeta)
            # actualizar los datos del vuelo
            vuelo.actualizar_datos()
            #vuelo.nombre = nombre
            #vuelo.datos.loc[vuelo.datos.dato=='nombre', 'valor'] = nombre
            #vuelo.info['nombre'] = nombre
            # crear mapa
            vuelo.crear_mapa(tamanio=(tamanio_mapa/100), mosaico=True, imagenes=True, poligono=True, plan_de_vuelo=True)
        
        else:
            vuelo = Vuelo(carpeta=carpeta, leer_bitacora=True, **kwargs)

            # si no hay un archivo bitacora.csv previo, preguntar nombre y descripción
            if not os.path.exists(os.path.join(vuelo.info['carpeta'], vuelo.bitacora_csv)):
                vuelo.importar(carpeta)
                vuelo.actualizar_datos()
                # preguntar el nombre del vuelo
                nombre_automatico = os.path.basename(carpeta)
                nombre = tkinter.simpledialog.askstring(
                    _('Nombre del vuelo'), 
                    '\n'+
                    _('Nombre sugerido')+':\n  '+
                    nombre_automatico+'\n', 
                    initialvalue=nombre_automatico)
                if nombre==None: nombre = nombre_automatico
                if nombre=='': nombre = nombre_automatico
                #vuelo.nombre = nombre
                #vuelo.datos.loc[vuelo.datos.dato=='nombre', 'valor'] = nombre
                vuelo.info['nombre'] = nombre
                # preguntar descripción del vuelo
                descripcion_automatica = generar_descripcion(vuelo)
                descripcion = tkinter.simpledialog.askstring(
                    _('Descripción del vuelo'), 
                    '\n'+
                    _('Descripción sugerida')+':\n  '+
                    descripcion_automatica+'\n', 
                    initialvalue=descripcion_automatica)
                if descripcion==None: descripcion = descripcion_automatica
                if descripcion=='': descripcion = descripcion_automatica
                #vuelo.descripcion = descripcion
                #vuelo.datos.loc[vuelo.datos.dato=='descripcion', 'valor'] = descripcion
                vuelo.info['descripcion'] = descripcion

            # si no hay un mapa bitacora.png previo, crearlo
            if not os.path.exists(os.path.join(vuelo.info['carpeta'], vuelo.bitacora_png)):
                vuelo.crear_mapa(tamanio=(tamanio_mapa/100), mosaico=True, imagenes=True, poligono=True, plan_de_vuelo=True)
        
        # cerrar la ventana con el mensaje de espera
        espera.destroy()

        # mostrar los datos del vuelo abierto/creado
        mostrar_vuelo(vuelo)


    def abrir_vuelo_desde_boton():
        #seleccion = listado_vuelos.curselection()
        seleccion = listado_vuelos.index(listado_vuelos.focus())
        global lista_vuelos
        carpeta = lista_vuelos.loc[seleccion, 'carpeta']
        abrir_vuelo(carpeta)


    def borrar_vuelo_desde_boton():
        #seleccion = listado_vuelos.curselection()[0]
        seleccion = listado_vuelos.index(listado_vuelos.focus())
        global lista_vuelos
        lista_vuelos = lista_vuelos.drop(seleccion).reset_index(drop=True)
        guardar_variables_inicio()
        mostrar_lista_vuelos()


    def salir():
        ''' función para salir del programa
        '''
        # guardar las variables de inicio
        guardar_variables_inicio()
        # salir
        ventana.quit()
        ventana.destroy()



    ####################################
    # FUNCIONES DE LA VENTANA DEL VUELO 

    def modificar_datos_del_vuelo(vuelo, ventana_vuelo):
        nombre = vuelo.info['nombre']
        descripcion = vuelo.info['descripcion']
        nuevo_nombre = tkinter.simpledialog.askstring(
            _('Modificar nombre del vuelo'), 
            '\n'+
            _('Nombre anterior')+':\n  '+
            nombre+'\n', 
            initialvalue=nombre,
            parent=ventana_vuelo
            )
        if nuevo_nombre==None: nuevo_nombre = nombre
        if nuevo_nombre=='': nuevo_nombre = nombre
        nueva_descripcion = tkinter.simpledialog.askstring(
            _('Modificar descripción del vuelo'), 
            '\n'+
            _('Descripción anterior')+':\n  '+
            descripcion+'\n', 
            initialvalue=descripcion,
            parent=ventana_vuelo
            )
        if nueva_descripcion==None: nueva_descripcion = descripcion
        if nueva_descripcion=='': nueva_descripcion = descripcion
        # si el nombre o la descripción se modificaron
        if (nuevo_nombre != nombre) or (nueva_descripcion != descripcion):
            # actualizar el nombre del vuelo
            #vuelo.nombre = nuevo_nombre
            #vuelo.descripcion = nueva_descripcion
            #vuelo.datos.loc[vuelo.datos.dato=='nombre', 'valor'] = nuevo_nombre
            #vuelo.datos.loc[vuelo.datos.dato=='descripcion', 'valor'] = nueva_descripcion
            vuelo.info['nombre'] = nuevo_nombre
            vuelo.info['descripcion'] = nueva_descripcion
            # guardar los datos
            guardar_vuelo(vuelo)
            # reabrir ventana
            ventana_vuelo.destroy()
            abrir_vuelo(vuelo.info['carpeta'], actualizar=False)


    def generar_descripcion(vuelo, formato='{fecha}, {hora}, {localidad}'):
        nombre = formato.format(
            localidad=vuelo.info['localidad'].split(',')[0],    # sólo el nombre de la ciudad
            fecha=vuelo.info['fecha'],
            hora=vuelo.info['hora'][0:5]    # solo la hora y los minutos
        )
        nombre = nombre.replace(', , ', ', ').strip(', ')
        return nombre


    def guardar_vuelo(vuelo):
        # guardar resultados
        vuelo.guardar_png()
        vuelo.guardar_csv()
        vuelo.guardar_kml()
        # actualizar lista de vuelos
        global lista_vuelos
        fecha=vuelo.info['fecha'],
        hora=vuelo.info['hora'][0:5]    # solo la hora y los minutos
        nombre = vuelo.info['nombre']
        descripcion = vuelo.info['descripcion']
        carpeta = vuelo.info['carpeta']
        if (len(lista_vuelos.loc[lista_vuelos['carpeta']==carpeta])==0):
            datos_vuelo = pd.DataFrame([[fecha, hora, nombre, descripcion, carpeta]], columns=lista_vuelos.columns)
            lista_vuelos = lista_vuelos.append(datos_vuelo, ignore_index=True)
            guardar_variables_inicio()
            mostrar_lista_vuelos()
        else:
            lista_vuelos.loc[lista_vuelos['carpeta']==carpeta, 'fecha'] = fecha
            lista_vuelos.loc[lista_vuelos['carpeta']==carpeta, 'hora'] = hora
            lista_vuelos.loc[lista_vuelos['carpeta']==carpeta, 'nombre'] = nombre
            lista_vuelos.loc[lista_vuelos['carpeta']==carpeta, 'descripcion'] = descripcion
            guardar_variables_inicio()
            mostrar_lista_vuelos()


    def actualizar_vuelo(vuelo, ventana_vuelo):
        ventana_vuelo.destroy()
        nombre = vuelo.info['nombre']
        descripcion = vuelo.info['descripcion']
        global idioma
        abrir_vuelo(vuelo.info['carpeta'], actualizar=True, nombre=nombre, descripcion=descripcion, idioma=idioma)

    def ver_archivos_del_vuelo(vuelo):
        carpeta = vuelo.info['carpeta']
        webbrowser.open('file:///' + carpeta)

    #####################
    # VENTANA DEL VUELO

    def mostrar_vuelo(vuelo):

        ventana_vuelo = tkinter.Toplevel()
        tamanio_mapa = 400   # tamaño del mapa, que define el tamaño de la ventana
        margen_x  = 5
        margen_y  = 5
        tam_y_botones = 50
        tam_x_ventana_vuelo = tamanio_mapa * 2 + margen_x * 2
        tam_y_ventana_vuelo = tam_y_botones + tamanio_mapa + margen_y * 3
        ventana_vuelo.wm_geometry("%dx%d" % (tam_x_ventana_vuelo, tam_y_ventana_vuelo))
        ventana_vuelo.configure(background='white')
        ventana_vuelo.title(vuelo.info['nombre'])
        ventana_vuelo.iconphoto(False, tkinter.PhotoImage(file='./_iconos/icono.png'))

        ##########
        # BOTONES

        alto_botones = 50
        ancho_botones = 170
        tam_y_marco_botones = alto_botones
        barra_botones = tkinter.Label(ventana_vuelo, background=color_fondo_franja_superior, bd=0).place(x=0, y=0, width=tam_x_ventana_vuelo, height=tam_y_marco_botones+margen_y*2)
        
        # BOTÓN GUARDAR
        # guarda los datos del vuelo
        global carpeta_iconos
        icono_guardar = tkinter.PhotoImage(file = os.path.join(carpeta_iconos, 'guardar_vuelo.png'))
        boton_guardar = tkinter.Button(
            master=ventana_vuelo, 
            text=_('Guardar vuelo'), command=lambda: guardar_vuelo(vuelo), image=icono_guardar, 
            anchor='w', compound="left", justify=tkinter.LEFT, font=('Arial', 11, 'bold'), wraplength=ancho_botones-icono_guardar.width()-15, 
            background=color_botones, activebackground=color_botones, foreground=color_texto_botones, activeforeground=color_texto_botones, 
            relief=tkinter.FLAT, cursor='hand2')
        boton_guardar.place(x=margen_x, y=margen_y, height=alto_botones, width=ancho_botones)
        
        # BOTÓN ACTUALIZAR
        # actualiza los datos del vuelo (crea nuevamente el vuelo a partir de los archivos de la carpeta)
        icono_actualizar = tkinter.PhotoImage(file = os.path.join(carpeta_iconos, 'actualizar_vuelo.png'))
        boton_actualizar = tkinter.Button(
            master=ventana_vuelo, 
            text=_('Actualizar vuelo'), command=lambda: actualizar_vuelo(vuelo, ventana_vuelo), image=icono_actualizar, 
            anchor='w', compound="left", justify=tkinter.LEFT, font=('Arial', 11, 'bold'), wraplength=ancho_botones-icono_actualizar.width()-15, 
            background=color_botones, activebackground=color_botones, foreground=color_texto_botones, activeforeground=color_texto_botones, 
            relief=tkinter.FLAT, cursor='hand2')
        boton_actualizar.place(x=margen_x+ancho_botones+margen_x, y=margen_y, height=alto_botones, width=ancho_botones)

        # BOTÓN MODIFICAR NOMBRE
        # actualiza los datos del vuelo (crea nuevamente el vuelo a partir de los archivos de la carpeta)
        icono_modificar = tkinter.PhotoImage(file = os.path.join(carpeta_iconos, 'modificar_vuelo.png'))
        boton_modificar = tkinter.Button(
            master=ventana_vuelo, 
            text=_('Modificar vuelo'), command=lambda: modificar_datos_del_vuelo(vuelo, ventana_vuelo), image=icono_modificar, 
            anchor='w', compound="left", justify=tkinter.LEFT, font=('Arial', 11, 'bold'), wraplength=ancho_botones-icono_modificar.width()-15, 
            background=color_botones, activebackground=color_botones, foreground=color_texto_botones, activeforeground=color_texto_botones, 
            relief=tkinter.FLAT, cursor='hand2')
        boton_modificar.place(x=margen_x+ancho_botones+margen_x+ancho_botones+margen_x, y=margen_y, height=alto_botones, width=ancho_botones)

        # BOTÓN VER ARCHIVOS
        # abre el explorador de archivos para visualizar la carpeta con los archivos del vuelo
        icono_ver_archivos = tkinter.PhotoImage(file = os.path.join(carpeta_iconos, 'ver_archivos_vuelo.png'))
        boton_ver_archivos = tkinter.Button(
            master=ventana_vuelo, 
            text=_('Explorar archivos'), command=lambda: ver_archivos_del_vuelo(vuelo), image=icono_ver_archivos, 
            anchor='w', compound="left", justify=tkinter.LEFT, font=('Arial', 11, 'bold'), wraplength=ancho_botones-icono_ver_archivos.width()-15, 
            background=color_botones, activebackground=color_botones, foreground=color_texto_botones, activeforeground=color_texto_botones, 
            relief=tkinter.FLAT, cursor='hand2')
        boton_ver_archivos.place(x=margen_x+ancho_botones+margen_x+ancho_botones+margen_x+ancho_botones+margen_x, y=margen_y, height=alto_botones, width=ancho_botones)


        ###########################
        # DATOS DEL VUELO

        tam_x_marco_datos = tam_x_ventana_vuelo - margen_x * 2
        tam_y_marco_datos = tamanio_mapa
        marco_datos = tkinter.Frame(ventana_vuelo, relief=tkinter.FLAT, width=tam_x_marco_datos, height=tam_y_marco_datos, borderwidth=0, highlightthickness=0)
        marco_datos.place(x=margen_x, y=margen_y+tam_y_marco_botones+margen_y)


        #######
        # MAPA

        tam_x_marco_mapa = tamanio_mapa
        tam_y_marco_mapa = tamanio_mapa
        # mostrar mapa
        #vuelo.crear_mapa(tamanio=(min(tam_x_marco_mapa, tam_y_marco_mapa)/100), mosaico=True, imagenes=True, poligono=True, plan_de_vuelo=True)
        imagen = ImageTk.PhotoImage(vuelo.mapa.resize((tamanio_mapa, tamanio_mapa)), master=ventana_vuelo)
        marco_mapa=tkinter.Label(marco_datos, image=imagen)
        marco_mapa.image = imagen
        marco_mapa.grid(row=0, column=0, sticky='NSEW')


        #################
        # TABLA DE DATOS
        
        marco_tabla=tkinter.Frame(marco_datos, relief=tkinter.FLAT, borderwidth=0, highlightthickness=0)
        marco_tabla.grid(row=0, column=1, sticky='NSEW')

        def desplazamiento_lienzo(event):
            lienzo_principal.configure(scrollregion=lienzo_principal.bbox("all"))

        tam_x_desplazamiento = 20
        tam_x_lienzo = tamanio_mapa - tam_x_desplazamiento
        tam_y_lienzo = tamanio_mapa
        lienzo_principal=tkinter.Canvas(marco_tabla, background='white', borderwidth=0, highlightthickness=0)
        marco_secundario=tkinter.Frame(lienzo_principal, background='white', borderwidth=0, highlightthickness=0)
        desplazamiento=tkinter.Scrollbar(marco_tabla,orient="vertical", width=tam_x_desplazamiento, command=lienzo_principal.yview)
        lienzo_principal.configure(yscrollcommand=desplazamiento.set, width=tam_x_lienzo, height=tam_y_lienzo)

        desplazamiento.pack(side="right",fill="y")
        lienzo_principal.pack(side="left")
        lienzo_principal.create_window((0,0),window=marco_secundario,anchor='nw')
        marco_secundario.bind("<Configure>", desplazamiento_lienzo)

        ancho_columna = ((tam_x_lienzo + margen_x) / 2) - margen_x

        redondeos = {
            'superficie_cubierta': 0,
            'altitud_de_vuelo': 0,
            'velocidad_de_vuelo': 1,
            'iso': 0,
            'exposicion': 5,
            'latitud': 2,
            'longitud': 2,
            'altitud': 0,
        }

        fila = 0
        for variable in vuelo.info:
            global idioma
            nombre_variable = vuelo.tabla_variables.loc[vuelo.tabla_variables['variable']==variable][idioma].values[0]
            valor = vuelo.info[variable]
            if str(valor)!=valor: valor=str(valor)
            if valor != '':
                if variable in redondeos:
                    formato = "{:."+str(redondeos[variable])+"f}"
                    valor_redondeado = round(float(valor), redondeos[variable])
                    valor = formato.format(valor_redondeado)
                tkinter.Label(marco_secundario, text=nombre_variable, background='white', wraplength=ancho_columna, justify='left').grid(column=0, row=fila, padx=margen_x, pady=margen_y/2, sticky='NW')
                tkinter.Label(marco_secundario, text=valor, background='white', wraplength=ancho_columna, justify='left').grid(column=1, row=fila, padx=margen_x, pady=margen_y/2, sticky='NW')
                fila += 1


        ventana_vuelo.mainloop()



    ######################
    # VARIABLES GENERALES


    # localización del programa
    ruta_programa             = inspect.getframeinfo(inspect.currentframe()).filename
    carpeta_programa          = os.path.dirname(os.path.abspath(ruta_programa))
    ruta_archivo_inicio       = os.path.join(carpeta_programa, '_configuracion', 'bitacora.ini')
    ruta_archivo_vuelos       = os.path.join(carpeta_programa, '_vuelos', 'vuelos.csv')
    ruta_archivo_traducciones = os.path.join(carpeta_programa, '_configuracion', 'textos_interfaz.xlsx')
    global carpeta_iconos
    carpeta_iconos            = os.path.join(carpeta_programa, '_iconos')
    carpeta_imagenes          = os.path.join(carpeta_programa, '_imagenes')

    # colores
    color_botones =                  '#d6e4ff'
    color_texto_botones =            '#5599ff' 
    color_fondo_franja_superior =   '#d6e4ff' #ccaaff'

    # idioma en que están escritos las cadenas de texto originales del programa
    global idioma_programa
    idioma_programa = 'es'

    # idioma de la interfaz
    global idioma

    # abrir textos y traducciones
    abrir_traducciones()

    # variables globales con datos del proyecto
    global ruta_vuelo
    global lista_vuelos
    lista_vuelos = pd.DataFrame(columns=['fecha', 'hora', 'nombre', 'carpeta'])

    # variables de inicio
    leer_variables_inicio()




    ####################
    # VENTANA PRINCIPAL
    
    # formato de la ventana principal
    ventana=tkinter.Tk()
    tam_x_ventana = 1024
    tam_y_ventana = 384
    pos_x_ventana = 50
    pos_y_ventana  = 10
    margen_x  = 5
    margen_y  = 5
    ventana.wm_geometry("%dx%d+%d+%d" % (tam_x_ventana, tam_y_ventana, pos_x_ventana, pos_y_ventana))
    ventana.configure(background='white')
    ventana.title('Bitácora')
    ventana.iconphoto(False, tkinter.PhotoImage(file='./_iconos/icono.png'))

    # si aún no se ha elegido el idioma, se muestra la ventana de selección de idioma
    if idioma == '-': 
        ventana.withdraw()
        elegir_idioma()
        ventana.update()
        ventana.deiconify()
        if idioma == '-':
            idioma = idioma_programa

    # título de la ventana traducido
    ventana.title(_('Bitácora'))


    ##########
    # BOTONES

    alto_botones = 50
    ancho_botones = 180
    tam_x_marco_botones = tam_x_ventana - margen_x * 2
    tam_y_marco_botones = alto_botones
    tkinter.Label(ventana, background=color_fondo_franja_superior, bd=0).place(x=0, y=0, width=tam_x_ventana, height=tam_y_marco_botones+margen_y*2)
    
    # BOTÓN NUEVO VUELO
    # abre un vuelo vacío (sin indicar carpeta)
    icono_nuevo_vuelo = tkinter.PhotoImage(file = os.path.join(carpeta_iconos, 'nuevo_vuelo.png'))
    boton_nuevo_vuelo = tkinter.Button(
        master=ventana, 
        text=_('Nuevo vuelo'), command=abrir_vuelo, image=icono_nuevo_vuelo, 
        anchor='w', compound="left", justify=tkinter.LEFT, font=('Arial', 11, 'bold'), wraplength=ancho_botones-alto_botones, 
        background=color_botones, activebackground=color_botones, foreground=color_texto_botones, activeforeground=color_texto_botones, 
        relief=tkinter.FLAT, cursor='hand2')
    boton_nuevo_vuelo.place(x=margen_x, y=margen_y, height=alto_botones, width=ancho_botones)
    
    # BOTÓN ABRIR VUELO
    # abre el vuelo seleccionado en el listado
    icono_abrir_vuelo = tkinter.PhotoImage(file = os.path.join(carpeta_iconos, 'ver_vuelo.png'))
    boton_abrir_vuelo = tkinter.Button(
        master=ventana, 
        text=_('Abrir vuelo'), command=abrir_vuelo_desde_boton, image=icono_abrir_vuelo, 
        anchor='w', compound="left", justify=tkinter.LEFT, font=('Arial', 11, 'bold'), wraplength=ancho_botones-alto_botones, 
        background=color_botones, activebackground=color_botones, foreground=color_texto_botones, activeforeground=color_texto_botones, 
        relief=tkinter.FLAT, cursor='hand2')
    boton_abrir_vuelo.place(x=margen_x+ancho_botones+margen_x, y=margen_y, height=alto_botones, width=ancho_botones)
    
    # BOTÓN BORRAR VUELO
    # elimina el vuelo seleccionado del listado
    icono_borrar_vuelo = tkinter.PhotoImage(file = os.path.join(carpeta_iconos, 'borrar_vuelo.png'))
    boton_borrar_vuelo = tkinter.Button(
        master=ventana, 
        text=_('Borrar vuelo'), command=borrar_vuelo_desde_boton, image=icono_borrar_vuelo, 
        anchor='w', compound="left", justify=tkinter.LEFT, font=('Arial', 11, 'bold'), wraplength=ancho_botones-alto_botones, 
        background=color_botones, activebackground=color_botones, foreground=color_texto_botones, activeforeground=color_texto_botones, 
        relief=tkinter.FLAT, cursor='hand2')
    boton_borrar_vuelo.place(x=margen_x+ancho_botones+margen_x+ancho_botones+margen_x, y=margen_y, height=alto_botones, width=ancho_botones)



    ####################
    # LISTADO DE VUELOS

    # barra de desplazamiento
    x, y = tam_x_ventana-20, margen_y+tam_y_marco_botones+margen_y
    scrollbar = tkinter.Scrollbar(ventana, relief=tkinter.FLAT)
    scrollbar.place(x=x, y=y, height=tam_y_ventana-y, width=20)

    # estilo de la tabla
    style = ttk.Style()
    style.configure("mystyle.Treeview", highlightthickness=0, bd=0, font=('Calibri', 11)) # fuente filas
    style.configure("mystyle.Treeview.Heading", font=('Calibri', 11), foreground=color_texto_botones) # fuente títulos
    style.layout("mystyle.Treeview", [('mystyle.Treeview.treearea', {'sticky': 'nswe'})]) # quitar bordes

    # crear tabla
    listado_vuelos = ttk.Treeview(ventana, selectmode='browse', style="mystyle.Treeview")
    listado_vuelos.configure(yscrollcommand=scrollbar.set)
    listado_vuelos.place(x=margen_x, y=y+margen_y, height=tam_y_ventana-y-margen_y*2, width=x-margen_x*2)
    scrollbar.config(command = listado_vuelos.yview)

    # columnas
    listado_vuelos["columns"] = ("1", "2", "3", "4")
    #listado_vuelos['show'] = 'headings'
    listado_vuelos.column("#0", width=44, anchor='c')
    listado_vuelos.column("1", width=100, anchor='c')
    listado_vuelos.column("2", width=60, anchor='c')
    listado_vuelos.column("3", width=250, anchor='w')
    listado_vuelos.column("4", width=550, anchor='w')
    listado_vuelos.heading("1", text=_("Fecha"))
    listado_vuelos.heading("2", text=_("Hora"))    
    listado_vuelos.heading("3", text=_("Nombre"))    
    listado_vuelos.heading("4", text=_("Descripción"))    

    mostrar_lista_vuelos()



    # asignar función 'salir' para cuando se cierre la ventana principal
    ventana.protocol("WM_DELETE_WINDOW", salir)

    # ejecutar la ventana principal
    ventana.mainloop()


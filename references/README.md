# References

Esta carpeta contiene material que ayuda a entender el proyecto, pero que no se ejecuta como parte del sistema principal.

| Ruta | Uso |
| --- | --- |
| `planta/plc_reader_y_app/` | Codigo real de planta usado como referencia para tags PLC, handshake y datos historicos. |
| `diseno/instrucciones/` | Material visual de apoyo para la interfaz. |
| `modelos_legacy/modelo/` | Artefactos ML anteriores al contrato CleaNet ONNX actual. |

No importar codigo desde esta carpeta en `brain` ni en `plc_gateway`. Si algun comportamiento de referencia debe pasar a produccion, copiar la idea al modulo operativo correspondiente y cubrirlo con pruebas.

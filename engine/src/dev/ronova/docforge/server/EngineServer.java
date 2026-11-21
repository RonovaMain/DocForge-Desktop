package dev.ronova.docforge.server;

import dev.ronova.docforge.core.DocFormat;
import dev.ronova.docforge.core.Engines;
import dev.ronova.docforge.core.OfficeEngine;
import dev.ronova.docforge.html.Html;
import java.io.BufferedInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.io.PrintStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.List;

/**
 * Движки DocForge (DOCX/XLSX/PPTX/ODT/ODS/ODP -> HTML и правка текста) как отдельный процесс для настольной версии.
 * Те же классы, что в Android-приложении, поэтому результат совпадает один в один.
 *
 * Протокол по stdin/stdout. Запрос — строка «КОМАНДА TAB арг TAB арг…», аргументы закодированы как в URL (%XX, UTF-8).
 * Ответ — «OK n» или «ERR n» и затем ровно n байт (результат или текст ошибки в UTF-8).
 *
 *   ping                              -> pong
 *   detect  путь имя                  -> DOCX | XLSX | PPTX | ODT | ODS | ODP | PDF
 *   render  путь имя                  -> HTML страницы
 *   text    путь имя id               -> текст элемента (для окна правки)
 *   display путь имя id               -> что показать в элементе после правки
 *   edit    путь имя id текст выход   -> записывает изменённый файл в «выход»
 *   pdfpages ШxВ,ШxВ,…                -> HTML-обёртка для PDF с такими размерами страниц (в пунктах)
 */
public final class EngineServer {
    private EngineServer() {
    }

    public static void main(String[] args) throws IOException {
        final OutputStream out = new java.io.BufferedOutputStream(new java.io.FileOutputStream(java.io.FileDescriptor.out), 1 << 16);
        System.setOut(new PrintStream(System.err, true, "UTF-8"));
        InputStream in = new BufferedInputStream(System.in, 1 << 16);
        while (true) {
            String line = readLine(in);
            if (line == null) {
                break;
            }
            if (line.isEmpty()) {
                continue;
            }
            byte[] body;
            boolean ok = true;
            try {
                body = handle(line.split("\t", -1));
            } catch (Throwable t) {
                ok = false;
                String msg = t.getMessage();
                body = (msg == null || msg.isEmpty() ? t.getClass().getSimpleName() : msg).getBytes(StandardCharsets.UTF_8);
            }
            out.write(((ok ? "OK " : "ERR ") + body.length + "\n").getBytes(StandardCharsets.US_ASCII));
            out.write(body);
            out.flush();
        }
    }

    static byte[] handle(String[] p) throws IOException {
        String cmd = p[0];
        switch (cmd) {
            case "ping":
                return "pong".getBytes(StandardCharsets.UTF_8);
            case "pdfpages": {
                List<int[]> sizes = new ArrayList<int[]>();
                String list = dec(p[1]);
                if (!list.isEmpty()) {
                    for (String s : list.split(",")) {
                        String[] wh = s.split("x");
                        sizes.add(new int[] {Integer.parseInt(wh[0]), Integer.parseInt(wh[1])});
                    }
                }
                return Html.pdfPages(sizes).getBytes(StandardCharsets.UTF_8);
            }
            default:
                break;
        }
        byte[] data = Files.readAllBytes(Paths.get(dec(p[1])));
        String name = dec(p[2]);
        DocFormat format = DocFormat.detect(name, data);
        if (cmd.equals("detect")) {
            return format.name().getBytes(StandardCharsets.UTF_8);
        }
        OfficeEngine engine = Engines.forFormat(format);
        switch (cmd) {
            case "render":
                return engine.renderHtml(data).getBytes(StandardCharsets.UTF_8);
            case "text": {
                String t = engine.textAt(data, dec(p[3]));
                if (t == null) {
                    throw new IllegalArgumentException("Элемент не найден");
                }
                return t.getBytes(StandardCharsets.UTF_8);
            }
            case "display": {
                String t = engine.displayAt(data, dec(p[3]));
                return (t == null ? "" : t).getBytes(StandardCharsets.UTF_8);
            }
            case "edit": {
                byte[] result = engine.editText(data, dec(p[3]), dec(p[4]));
                Files.write(Paths.get(dec(p[5])), result);
                return new byte[0];
            }
            default:
                throw new IllegalArgumentException("Неизвестная команда: " + cmd);
        }
    }

    private static String readLine(InputStream in) throws IOException {
        ByteArrayOutputStream buf = new ByteArrayOutputStream();
        int b;
        while ((b = in.read()) >= 0) {
            if (b == '\n') {
                return new String(buf.toByteArray(), StandardCharsets.UTF_8);
            }
            buf.write(b);
        }
        return buf.size() == 0 ? null : new String(buf.toByteArray(), StandardCharsets.UTF_8);
    }

    /** Аргументы приходят в ASCII: всё, кроме безопасных символов, закодировано как %XX по байтам UTF-8. */
    static String dec(String s) {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream(s.length());
        for (int i = 0; i < s.length(); i++) {
            char c = s.charAt(i);
            if (c == '%' && i + 2 <= s.length() - 1) {
                bytes.write(Integer.parseInt(s.substring(i + 1, i + 3), 16));
                i += 2;
            } else {
                bytes.write(c);
            }
        }
        return new String(bytes.toByteArray(), StandardCharsets.UTF_8);
    }
}

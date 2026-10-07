<?xml version="1.0" encoding="utf-8"?>
<!--
  Human-readable preview for locally opened feeds/*.xml in Firefox.

  Firefox only supports XSLT 1.0 and lacks disable-output-escaping, so the
  escaped HTML in content:encoded cannot be re-rendered by XSLT alone. Each
  item's content therefore lands in a hidden div, and the inline script below
  injects it via innerHTML (renders every carousel slide and <video> tag).
  With JS disabled, a <noscript> fallback shows the enclosure cover image and
  the plain-text description.

  This file must sit next to the feed XMLs: file:// documents may load
  stylesheets from their own directory only.
-->
<xsl:stylesheet
    version="1.0"
    xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
    xmlns:content="http://purl.org/rss/1.0/modules/content/"
    exclude-result-prefixes="content">

  <xsl:output method="html" encoding="utf-8" indent="yes"/>

  <xsl:template match="/rss/channel">
    <html lang="en">
      <head>
        <meta charset="utf-8"/>
        <meta name="viewport" content="width=device-width, initial-scale=1"/>
        <title><xsl:value-of select="title"/></title>
        <style>
          body { font-family: system-ui, sans-serif; line-height: 1.5;
                 max-width: 42em; margin: 0 auto; padding: 1em; }
          h1 { font-size: 1.4em; margin-bottom: 0; }
          h2 { font-size: 1.1em; margin: 0 0 0.2em; }
          .meta { color: #777; font-size: 0.85em; margin: 0.2em 0; }
          .item { border-top: 1px solid #ccc; padding: 1.2em 0; }
          img, video { max-width: 100%; height: auto; display: block;
                       margin: 0.5em 0; }
          .raw-content { display: none; }
          pre { overflow-x: auto; background: #f4f4f4; padding: 0.5em; }
        </style>
      </head>
      <body>
        <header>
          <h1><xsl:value-of select="title"/></h1>
          <p class="meta">built <xsl:value-of select="lastBuildDate"/></p>
          <p class="meta"><a href="{link}"><xsl:value-of select="link"/></a></p>
          <p><xsl:value-of select="description"/></p>
        </header>
        <xsl:apply-templates select="item"/>
        <script>
          document.querySelectorAll(".raw-content").forEach(function (el) {
            el.nextElementSibling.innerHTML = el.textContent;
            el.remove();
          });
        </script>
      </body>
    </html>
  </xsl:template>

  <xsl:template match="item">
    <article class="item">
      <h2><a href="{link}"><xsl:value-of select="title"/></a></h2>
      <p class="meta"><xsl:value-of select="pubDate"/></p>
      <div class="raw-content"><xsl:value-of select="content:encoded"/></div>
      <div class="rendered"></div>
      <noscript>
        <p>
          <xsl:if test="enclosure/@url">
            <img src="{enclosure/@url}" alt="cover image"/>
          </xsl:if>
        </p>
        <p><xsl:value-of select="description"/></p>
        <p class="meta">JavaScript is off: showing cover image only.</p>
      </noscript>
    </article>
  </xsl:template>

</xsl:stylesheet>

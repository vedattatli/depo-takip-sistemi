/* Depo Takip - hareket satirlari ve urun arama */

(function () {
  "use strict";

  // --------------------------------------------------------------- urun arama
  function depoDegeri() {
    var alan = document.querySelector("[data-depo-kaynak]");
    return alan && alan.value ? alan.value : "";
  }

  function oneriGoster(kutu, kayitlar, secHandler) {
    kutu.innerHTML = "";
    if (!kayitlar.length) {
      kutu.innerHTML = '<div class="bos">Sonuç yok</div>';
      kutu.style.display = "block";
      return;
    }
    kayitlar.forEach(function (k, i) {
      var d = document.createElement("div");
      d.className = "satir" + (i === 0 ? " secili" : "");
      var detay = [k.sku, k.renk, k.olcu].filter(Boolean).join(" · ");
      d.innerHTML =
        '<div class="ad"></div><div class="detay"></div>';
      d.querySelector(".ad").textContent = k.ad;
      d.querySelector(".detay").textContent =
        detay + " — stok: " + k.kullanilabilir + " " + k.birim;
      d.addEventListener("mousedown", function (e) {
        e.preventDefault();
        secHandler(k);
      });
      kutu.appendChild(d);
    });
    kutu.style.display = "block";
  }

  function aramaBagla(hucre) {
    var girdi = hucre.querySelector(".urun-arama");
    var gizli = hucre.querySelector(".varyant-id");
    var kutu = hucre.querySelector(".oneri-kutu");
    var bilgi = hucre.querySelector(".secim-bilgi");
    if (!girdi || girdi.dataset.bagli) return;
    girdi.dataset.bagli = "1";

    var zamanlayici = null;
    var sonKayitlar = [];

    function sec(k) {
      gizli.value = k.id;
      girdi.value = k.ad + (k.renk ? " / " + k.renk : "");
      if (bilgi) {
        bilgi.innerHTML = "";
        var b = document.createElement("span");
        b.className = "kucuk";
        b.textContent = k.sku + " · stok " + k.kullanilabilir + " " + k.birim;
        bilgi.appendChild(b);
      }
      kutu.style.display = "none";
      var miktar = hucre.closest("tr").querySelector(".miktar-alan");
      if (miktar) miktar.focus();
      satirGerekiyorMu();
    }

    girdi.addEventListener("input", function () {
      gizli.value = "";
      if (bilgi) bilgi.textContent = "";
      clearTimeout(zamanlayici);
      var q = girdi.value.trim();
      if (q.length < 2) {
        kutu.style.display = "none";
        return;
      }
      zamanlayici = setTimeout(function () {
        var url = "/stok/ara?q=" + encodeURIComponent(q);
        var depo = depoDegeri();
        if (depo) url += "&depo=" + depo;
        fetch(url)
          .then(function (r) { return r.json(); })
          .then(function (kayitlar) {
            sonKayitlar = kayitlar;
            oneriGoster(kutu, kayitlar, sec);
          })
          .catch(function () { kutu.style.display = "none"; });
      }, 220);
    });

    girdi.addEventListener("keydown", function (e) {
      if (kutu.style.display !== "block") return;
      // Bazi tarayici/klavye duzenlerinde e.key gelmeyebiliyor, keyCode'a da bakiyoruz
      var asagi = e.key === "ArrowDown" || e.keyCode === 40;
      var yukari = e.key === "ArrowUp" || e.keyCode === 38;
      var onayla = e.key === "Enter" || e.keyCode === 13;
      var vazgec = e.key === "Escape" || e.keyCode === 27;
      var secili = kutu.querySelector(".satir.secili");
      if (asagi || yukari) {
        e.preventDefault();
        var hepsi = Array.prototype.slice.call(kutu.querySelectorAll(".satir"));
        var i = hepsi.indexOf(secili);
        var yeni = asagi ? i + 1 : i - 1;
        if (yeni < 0) yeni = hepsi.length - 1;
        if (yeni >= hepsi.length) yeni = 0;
        if (secili) secili.classList.remove("secili");
        if (hepsi[yeni]) {
          hepsi[yeni].classList.add("secili");
          hepsi[yeni].scrollIntoView({ block: "nearest" });
        }
      } else if (onayla) {
        // Oneri listesi acikken Enter formu gondermemeli, secim yapmali
        e.preventDefault();
        if (secili) {
          var idx = Array.prototype.slice
            .call(kutu.querySelectorAll(".satir"))
            .indexOf(secili);
          if (sonKayitlar[idx]) sec(sonKayitlar[idx]);
        }
      } else if (vazgec) {
        kutu.style.display = "none";
      }
    });

    girdi.addEventListener("blur", function () {
      setTimeout(function () { kutu.style.display = "none"; }, 120);
    });
  }

  // ------------------------------------------------------------ satir yonetimi
  function satirEkle(odakla) {
    var govde = document.querySelector("#satirlar tbody");
    var kalip = document.querySelector("#satir-kalibi");
    if (!govde || !kalip) return null;
    var yeni = kalip.content.cloneNode(true);
    govde.appendChild(yeni);
    var satir = govde.lastElementChild;
    aramaBagla(satir.querySelector(".urun-hucre"));
    numaralandir();
    if (odakla) satir.querySelector(".urun-arama").focus();
    return satir;
  }

  function numaralandir() {
    var satirlar = document.querySelectorAll("#satirlar tbody tr");
    satirlar.forEach(function (tr, i) {
      var no = tr.querySelector(".satir-no");
      if (no) no.textContent = i + 1;
    });
  }

  function satirGerekiyorMu() {
    // Son satir doldurulduysa otomatik yeni bos satir ac
    var satirlar = document.querySelectorAll("#satirlar tbody tr");
    if (!satirlar.length) return;
    var son = satirlar[satirlar.length - 1];
    var vid = son.querySelector(".varyant-id");
    if (vid && vid.value) satirEkle(false);
  }

  document.addEventListener("click", function (e) {
    var ekle = e.target.closest("[data-satir-ekle]");
    if (ekle) {
      e.preventDefault();
      satirEkle(true);
      return;
    }
    var sil = e.target.closest(".sil-dugme");
    if (sil) {
      e.preventDefault();
      var govde = document.querySelector("#satirlar tbody");
      if (govde.querySelectorAll("tr").length > 1) {
        sil.closest("tr").remove();
      } else {
        var tr = sil.closest("tr");
        tr.querySelector(".varyant-id").value = "";
        tr.querySelector(".urun-arama").value = "";
        tr.querySelector(".miktar-alan").value = "";
        var b = tr.querySelector(".secim-bilgi");
        if (b) b.textContent = "";
      }
      numaralandir();
    }
  });

  // --------------------------------------------------------------- barkod okut
  // El terminali okuttugu kodu klavyeden yazip Enter'a basar. Biz de bu kutuda
  // Enter'i yakalayip kodu urune cevirip satira ekliyoruz.
  function barkodBagla() {
    var kutu = document.querySelector("#barkod-okut");
    if (!kutu) return;
    var durum = document.querySelector("#barkod-durum");

    function bildir(mesaj, tur) {
      if (!durum) return;
      durum.textContent = mesaj;
      durum.className = "kucuk barkod-durum " + (tur || "");
    }

    function bosSatirBul() {
      var satirlar = document.querySelectorAll("#satirlar tbody tr");
      for (var i = 0; i < satirlar.length; i++) {
        var vid = satirlar[i].querySelector(".varyant-id");
        if (vid && !vid.value) return satirlar[i];
      }
      return satirEkle(false);
    }

    function satiraYaz(kayit) {
      // Ayni urun zaten satirda varsa miktarini artir, yeni satir acma
      var mevcutlar = document.querySelectorAll("#satirlar tbody tr");
      for (var i = 0; i < mevcutlar.length; i++) {
        var vid = mevcutlar[i].querySelector(".varyant-id");
        if (vid && vid.value === String(kayit.id)) {
          var m = mevcutlar[i].querySelector(".miktar-alan");
          var sayi = parseFloat((m.value || "0").replace(",", ".")) || 0;
          m.value = sayi + 1;
          m.focus();
          m.select();
          bildir(kayit.ad + " — miktar " + m.value + " oldu", "iyi");
          return;
        }
      }

      var satir = bosSatirBul();
      if (!satir) return;
      satir.querySelector(".varyant-id").value = kayit.id;
      satir.querySelector(".urun-arama").value =
        kayit.ad + (kayit.renk ? " / " + kayit.renk : "");
      var bilgi = satir.querySelector(".secim-bilgi");
      if (bilgi) bilgi.textContent = kayit.sku + " · stok " + kayit.kullanilabilir + " " + kayit.birim;
      var miktar = satir.querySelector(".miktar-alan");
      miktar.value = "1";
      miktar.focus();
      miktar.select();
      bildir("✓ " + kayit.ad + (kayit.renk ? " / " + kayit.renk : "") + " eklendi", "iyi");
      satirGerekiyorMu();
    }

    kutu.addEventListener("keydown", function (e) {
      if (!(e.key === "Enter" || e.keyCode === 13)) return;
      e.preventDefault();
      var kod = kutu.value.trim();
      if (!kod) return;
      var url = "/barkod/oku?kod=" + encodeURIComponent(kod);
      var depo = depoDegeri();
      if (depo) url += "&depo=" + depo;
      fetch(url)
        .then(function (r) { return r.json(); })
        .then(function (kayit) {
          kutu.value = "";
          if (kayit.bulundu) satiraYaz(kayit);
          else bildir("✗ " + kayit.mesaj, "kotu");
        })
        .catch(function () { bildir("Okuma başarısız, tekrar deneyin.", "kotu"); });
    });
  }

  // ------------------------------------------------------- sayimda barkod okut
  // Sayarken listede ilgili satiri aramak vakit kaybi; okutunca o satira atlar.
  // "Okuttukca 1 artir" isaretliyse her okutma sayilan miktari bir artirir —
  // tek tek sayilan hirdavat icin en hizli yontem bu.
  function sayimBarkodBagla() {
    var kutu = document.querySelector("#sayim-barkod");
    if (!kutu) return;
    var durum = document.querySelector("#sayim-barkod-durum");
    var tally = document.querySelector("#sayim-tally");

    function bildir(mesaj, tur) {
      if (!durum) return;
      durum.textContent = mesaj;
      durum.className = "kucuk barkod-durum " + (tur || "");
    }

    kutu.addEventListener("keydown", function (e) {
      if (!(e.key === "Enter" || e.keyCode === 13)) return;
      e.preventDefault();
      var kod = kutu.value.trim();
      if (!kod) return;
      fetch("/barkod/oku?kod=" + encodeURIComponent(kod))
        .then(function (r) { return r.json(); })
        .then(function (kayit) {
          kutu.value = "";
          if (!kayit.bulundu) { bildir("✗ " + kayit.mesaj, "kotu"); return; }
          var alan = document.querySelector(
            '.sayim-alan[data-varyant="' + kayit.id + '"]');
          if (!alan) {
            bildir("✗ " + kayit.ad + " bu sayım listesinde yok (filtre açık olabilir)",
                   "kotu");
            return;
          }
          alan.scrollIntoView({ block: "center", behavior: "smooth" });
          alan.closest("tr").style.background = "#fffbe6";
          if (tally && tally.checked) {
            var sayi = parseFloat((alan.value || "0").replace(",", ".")) || 0;
            alan.value = sayi + 1;
            bildir("✓ " + kayit.ad + " → " + alan.value, "iyi");
          } else {
            alan.focus();
            alan.select();
            bildir("✓ " + kayit.ad + " — miktarı yazın", "iyi");
          }
        })
        .catch(function () { bildir("Okuma başarısız, tekrar deneyin.", "kotu"); });
    });
  }

  // ------------------------------------------------------------------ baslat
  document.addEventListener("DOMContentLoaded", function () {
    barkodBagla();
    sayimBarkodBagla();

    // Tablo basligindaki "hepsini seç" kutusu
    var hepsiKutu = document.querySelector("[data-hepsini-sec]");
    if (hepsiKutu) {
      hepsiKutu.addEventListener("change", function () {
        document.querySelectorAll("tbody input[type=checkbox][name=varyant_id]")
          .forEach(function (k) { k.checked = hepsiKutu.checked; });
      });
    }

    document.querySelectorAll(".urun-hucre").forEach(aramaBagla);
    if (document.querySelector("#satirlar")) {
      if (!document.querySelectorAll("#satirlar tbody tr").length) satirEkle(false);
      numaralandir();
    }

    // Depo degisince secili urunlerin stok bilgisi yaniltici olmasin
    var depoAlan = document.querySelector("[data-depo-kaynak]");
    if (depoAlan) {
      depoAlan.addEventListener("change", function () {
        document.querySelectorAll(".secim-bilgi").forEach(function (b) {
          if (b.textContent) b.textContent = "depo değişti — stok yeniden kontrol edilecek";
        });
      });
    }

    // Onay isteyen formlar
    document.querySelectorAll("form[data-onay]").forEach(function (f) {
      f.addEventListener("submit", function (e) {
        if (!confirm(f.dataset.onay)) e.preventDefault();
      });
    });

    // Filtre kutularinda degisiklik olunca formu gonder
    document.querySelectorAll("[data-otomatik-gonder]").forEach(function (alan) {
      alan.addEventListener("change", function () { alan.form.submit(); });
    });

    // Sayim ekraninda Enter ile bir alt satira gec
    document.querySelectorAll(".sayim-alan").forEach(function (alan, i, hepsi) {
      alan.addEventListener("keydown", function (e) {
        if (e.key === "Enter") {
          e.preventDefault();
          if (hepsi[i + 1]) { hepsi[i + 1].focus(); hepsi[i + 1].select(); }
          else alan.form.submit();
        }
      });
    });
  });
})();

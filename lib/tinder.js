export function extractUsername(input) {
  const text = input.trim();
  const urlPattern = /(?:https?:\/\/)?(?:www\.)?tinder\.com\/@([a-zA-Z0-9_]+)/i;
  const match = text.match(urlPattern);
  if (match) {
    return match[1];
  }
  if (/^@?[a-zA-Z0-9_]+$/.test(text)) {
    return text.replace(/^@/, '');
  }
  return null;
}

// Pure JavaScript MD5 Implementation (Zero Dependencies for Cloudflare Worker V8)
function md5(string) {
  function rotateLeft(lValue, iShiftBits) { return (lValue << iShiftBits) | (lValue >>> (32 - iShiftBits)); }
  function addUnsigned(lX, lY) {
    var lX4, lY4, lX8, lY8, lResult;
    lX8 = lX & 0x80000000; lY8 = lY & 0x80000000;
    lX4 = lX & 0x40000000; lY4 = lY & 0x40000000;
    lResult = (lX & 0x3fffffff) + (lY & 0x3fffffff);
    if (lX4 & lY4) return lResult ^ 0x80000000 ^ lX8 ^ lY8;
    if (lX4 | lY4) {
      if (lResult & 0x40000000) return lResult ^ 0xc0000000 ^ lX8 ^ lY8;
      else return lResult ^ 0x40000000 ^ lX8 ^ lY8;
    } else return lResult ^ lX8 ^ lY8;
  }
  function F(x, y, z) { return (x & y) | (~x & z); }
  function G(x, y, z) { return (x & z) | (y & ~z); }
  function H(x, y, z) { return x ^ y ^ z; }
  function I(x, y, z) { return y ^ (x | ~z); }
  function FF(a, b, c, d, x, s, ac) { a = addUnsigned(a, addUnsigned(addUnsigned(F(b, c, d), x), ac)); return addUnsigned(rotateLeft(a, s), b); }
  function GG(a, b, c, d, x, s, ac) { a = addUnsigned(a, addUnsigned(addUnsigned(G(b, c, d), x), ac)); return addUnsigned(rotateLeft(a, s), b); }
  function HH(a, b, c, d, x, s, ac) { a = addUnsigned(a, addUnsigned(addUnsigned(H(b, c, d), x), ac)); return addUnsigned(rotateLeft(a, s), b); }
  function II(a, b, c, d, x, s, ac) { a = addUnsigned(a, addUnsigned(addUnsigned(I(b, c, d), x), ac)); return addUnsigned(rotateLeft(a, s), b); }
  function convertToWordArray(string) {
    var lWordCount, lMessageLength = string.length, lNumberOfWords_temp1 = lMessageLength + 8;
    var lNumberOfWords_temp2 = (lNumberOfWords_temp1 - (lNumberOfWords_temp1 % 64)) / 64;
    var lNumberOfWords = (lNumberOfWords_temp2 + 1) * 16, lWordArray = Array(lNumberOfWords - 1), lBytePosition = 0, lByteCount = 0;
    while (lByteCount < lMessageLength) {
      lWordCount = (lByteCount - (lByteCount % 4)) / 4; lBytePosition = (lByteCount % 4) * 8;
      lWordArray[lWordCount] = (lWordArray[lWordCount] | (string.charCodeAt(lByteCount) << lBytePosition));
      lByteCount++;
    }
    lWordCount = (lByteCount - (lByteCount % 4)) / 4; lBytePosition = (lByteCount % 4) * 8;
    lWordArray[lWordCount] = lWordArray[lWordCount] | (0x80 << lBytePosition);
    lWordArray[lNumberOfWords - 2] = lMessageLength << 3; lWordArray[lNumberOfWords - 1] = lMessageLength >>> 29;
    return lWordArray;
  }
  function wordToHex(lValue) {
    var WordToHexValue = '', WordToHexValue_temp = '', lByte, lCount;
    for (lCount = 0; lCount <= 3; lCount++) {
      lByte = (lValue >>> (lCount * 8)) & 255;
      WordToHexValue_temp = '0' + lByte.toString(16);
      WordToHexValue = WordToHexValue + WordToHexValue_temp.substr(WordToHexValue_temp.length - 2, 2);
    }
    return WordToHexValue;
  }
  var x = Array(), k, AA, BB, CC, DD, a, b, c, d;
  var S11 = 7, S12 = 12, S13 = 17, S14 = 22, S21 = 5, S22 = 9, S23 = 14, S24 = 20, S31 = 4, S32 = 11, S33 = 16, S34 = 23, S41 = 6, S42 = 10, S43 = 15, S44 = 21;
  string = utf8Encode(string); x = convertToWordArray(string);
  a = 0x67452301; b = 0xEFCDAB89; c = 0x98BADCFE; d = 0x10325476;
  for (k = 0; k < x.length; k += 16) {
    AA = a; BB = b; CC = c; DD = d;
    a = FF(a, b, c, d, x[k + 0], S11, 0xD76AA478); d = FF(d, a, b, c, x[k + 1], S12, 0xE8C7B756); c = FF(c, d, a, b, x[k + 2], S13, 0x242070DB); b = FF(b, c, d, a, x[k + 3], S14, 0xC1BDCEEE);
    a = FF(a, b, c, d, x[k + 4], S11, 0xF57C0FAF); d = FF(d, a, b, c, x[k + 5], S12, 0x4787C62A); c = FF(c, d, a, b, x[k + 6], S13, 0xA8304613); b = FF(b, c, d, a, x[k + 7], S14, 0xFD469501);
    a = FF(a, b, c, d, x[k + 8], S11, 0x698098D8); d = FF(d, a, b, c, x[k + 9], S12, 0x8B44F7AF); c = FF(c, d, a, b, x[k + 10], S13, 0xFFFF5BB1); b = FF(b, c, d, a, x[k + 11], S14, 0x895CD7BE);
    a = FF(a, b, c, d, x[k + 12], S11, 0x6B901122); d = FF(d, a, b, c, x[k + 13], S12, 0xFD987193); c = FF(c, d, a, b, x[k + 14], S13, 0xA679438E); b = FF(b, c, d, a, x[k + 15], S14, 0x49B40821);
    a = GG(a, b, c, d, x[k + 1], S21, 0xF61E2562); d = GG(d, a, b, c, x[k + 6], S22, 0xC040B340); c = GG(c, d, a, b, x[k + 11], S23, 0x265E5A51); b = GG(b, c, d, a, x[k + 0], S24, 0xE9B6C7AA);
    a = GG(a, b, c, d, x[k + 5], S21, 0xD62F105D); d = GG(d, a, b, c, x[k + 10], S22, 0x02441453); c = GG(c, d, a, b, x[k + 15], S23, 0xD8A1E681); b = GG(b, c, d, a, x[k + 4], S24, 0xE7D3FBC8);
    a = GG(a, b, c, d, x[k + 9], S21, 0x21E1CDE6); d = GG(d, a, b, c, x[k + 14], S22, 0xC33707D6); c = GG(c, d, a, b, x[k + 3], S23, 0xF4D50D87); b = GG(b, c, d, a, x[k + 8], S24, 0x455A14ED);
    a = GG(a, b, c, d, x[k + 13], S21, 0xA9E3E905); d = GG(d, a, b, c, x[k + 2], S22, 0xFCEFA3F8); c = GG(c, d, a, b, x[k + 7], S23, 0x676F02D9); b = GG(b, c, d, a, x[k + 12], S24, 0x8D2A4C8A);
    a = HH(a, b, c, d, x[k + 5], S31, 0xFFFA3942); d = HH(d, a, b, c, x[k + 8], S32, 0x8771F681); c = HH(c, d, a, b, x[k + 11], S33, 0x6D9D6122); b = HH(b, c, d, a, x[k + 14], S34, 0xFDE5380C);
    a = HH(a, b, c, d, x[k + 1], S31, 0xA4BEEA44); d = HH(d, a, b, c, x[k + 4], S32, 0x4BDECFA9); c = HH(c, d, a, b, x[k + 7], S33, 0xF6BB4B60); b = HH(b, c, d, a, x[k + 10], S34, 0xBEBFBC70);
    a = HH(a, b, c, d, x[k + 13], S31, 0x289B7EC6); d = HH(d, a, b, c, x[k + 0], S32, 0xEAA127FA); c = HH(c, d, a, b, x[k + 3], S33, 0xD4EF3085); b = HH(b, c, d, a, x[k + 6], S34, 0x04881D05);
    a = HH(a, b, c, d, x[k + 9], S31, 0xD9D4D039); d = HH(d, a, b, c, x[k + 12], S32, 0xE6DB99E5); c = HH(c, d, a, b, x[k + 15], S33, 0x1FA27CF8); b = HH(b, c, d, a, x[k + 2], S34, 0xC4AC5665);
    a = II(a, b, c, d, x[k + 0], S41, 0xF4292244); d = II(d, a, b, c, x[k + 7], S42, 0x432AFF97); c = II(c, d, a, b, x[k + 14], S43, 0xAB9423A7); b = II(b, c, d, a, x[k + 5], S44, 0xFC93A039);
    a = II(a, b, c, d, x[k + 12], S41, 0x655B59C3); d = II(d, a, b, c, x[k + 3], S42, 0x8F0CCC92); c = II(c, d, a, b, x[k + 10], S43, 0xFFEFF47D); b = II(b, c, d, a, x[k + 1], S44, 0x85845DD1);
    a = II(a, b, c, d, x[k + 8], S41, 0x6FA87E4F); d = II(d, a, b, c, x[k + 15], S42, 0xFE2CE6E0); c = II(c, d, a, b, x[k + 6], S43, 0xA3014314); b = II(b, c, d, a, x[k + 13], S44, 0x4E0811A1);
    a = II(a, b, c, d, x[k + 4], S41, 0xF7537E82); d = II(d, a, b, c, x[k + 11], S42, 0xBD3AF235); c = II(c, d, a, b, x[k + 2], S43, 0x2AD7D2BB); b = II(b, c, d, a, x[k + 9], S44, 0xEB86D391);
    a = addUnsigned(a, AA); b = addUnsigned(b, BB); c = addUnsigned(c, CC); d = addUnsigned(d, DD);
  }
  return (wordToHex(a) + wordToHex(b) + wordToHex(c) + wordToHex(d)).toLowerCase();
}

function utf8Encode(string) {
  string = string.replace(/\r\n/g, '\n'); var utftext = '';
  for (var n = 0; n < string.length; n++) {
    var c = string.charCodeAt(n);
    if (c < 128) utftext += String.fromCharCode(c);
    else if ((c > 127) && (c < 2048)) { utftext += String.fromCharCode((c >> 6) | 192); utftext += String.fromCharCode((c & 63) | 128); }
    else { utftext += String.fromCharCode((c >> 12) | 224); utftext += String.fromCharCode(((c >> 6) & 63) | 128); utftext += String.fromCharCode((c & 63) | 128); }
  }
  return utftext;
}

export class TinderClient {
  constructor() {
    this.apiEndpoints = [
      "https://shieracc.com/getUser.php",
      "https://tinder6.com/getUser.php"
    ];
    this.baseUrl = "https://tinder.com";
    this.headers = {
      "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
      "Referer": "https://shieracc.com/Tinder_user.html"
    };
  }

  async getProfileData(username) {
    const t = Date.now();
    const sign = md5("asd94" + username + t);

    for (const apiEndpoint of this.apiEndpoints) {
      try {
        const url = `${apiEndpoint}?user=${encodeURIComponent(username)}&t=${t}&sign=${sign}`;
        const response = await fetch(url, {
          method: "GET",
          headers: this.headers,
        });

        if (response.status === 200) {
          const data = await response.json();
          if (data && typeof data === 'object') {
            const alive = Boolean(data.alive);
            const accountOk = Boolean(data.accountOk);
            const photosList = Array.isArray(data.photos) ? data.photos : [];

            if (data.birthDate || data.name || photosList.length > 0) {
              const name = String(data.name || "Hidden");
              const age = String(data.age || "Unknown");
              const birthDateVal = String(data.birthDate || "Hidden");
              const photosCount = photosList.length;
              const imageUrl = photosList[0] || "";
              const isRestricted = alive && !accountOk;

              // Extract Mongo Account ID from photo CDN link
              let accountId = null;
              if (photosList.length > 0) {
                const idMatch = photosList[0].match(/gotinder\.com\/([a-f0-9]{24})\//);
                if (idMatch) {
                  accountId = idMatch[1];
                }
              }

              let creationDate = "Not available";
              let accountAge = "Not available";
              let dt = null;

              if (data.regtime) {
                try {
                  dt = new Date(data.regtime + " UTC");
                  if (!isNaN(dt.getTime())) {
                    creationDate = data.regtime + " UTC";
                  } else {
                    dt = null;
                  }
                } catch (e) {}
              }

              if (!dt && accountId) {
                try {
                  const timestamp = parseInt(accountId.substring(0, 8), 16);
                  dt = new Date(timestamp * 1000);
                  creationDate = dt.getUTCFullYear() + '-' + 
                                 String(dt.getUTCMonth() + 1).padStart(2, '0') + '-' + 
                                 String(dt.getUTCDate()).padStart(2, '0') + ' ' + 
                                 String(dt.getUTCHours()).padStart(2, '0') + ':' + 
                                 String(dt.getUTCMinutes()).padStart(2, '0') + ':' + 
                                 String(dt.getUTCSeconds()).padStart(2, '0') + ' UTC';
                } catch (e) {}
              }

              if (dt && !isNaN(dt.getTime())) {
                const deltaMs = Date.now() - dt.getTime();
                const totalDays = Math.floor(deltaMs / (1000 * 60 * 60 * 24));
                const years = Math.floor(totalDays / 365);
                const months = Math.floor((totalDays % 365) / 30);
                const days = (totalDays % 365) % 30;

                if (years > 0) {
                  accountAge = `${years}y ${months}m ${days}d`;
                } else if (months > 0) {
                  accountAge = `${months}m ${days}d`;
                } else {
                  accountAge = `${days}d`;
                }
              }

              const domainName = apiEndpoint.split("//")[1].split("/")[0];

              return {
                status: "success",
                username,
                name,
                age,
                birth_date: birthDateVal,
                is_restricted: isRestricted,
                image_url: imageUrl,
                account_id: accountId || "Hidden",
                account_age: accountAge,
                creation_date: creationDate,
                photos_count: photosCount,
                verified: Boolean(data.verified),
                token_status: `api (${domainName})`
              };
            } else if (!alive || !accountOk) {
              const domainName = apiEndpoint.split("//")[1].split("/")[0];
              return {
                status: "not_found",
                username,
                name: "Hidden",
                age: "Unknown",
                birth_date: "Hidden",
                is_restricted: true,
                image_url: "",
                account_age: "Unknown",
                creation_date: "Unknown",
                photos_count: 0,
                verified: false,
                token_status: `api (${domainName})`
              };
            }
          }
        }
      } catch (err) {
        console.error(`API ${apiEndpoint} failed:`, err);
        continue;
      }
    }

    // 2. Fall back to scraping public profile
    return await this._scrapePublicProfile(username);
  }

  async _scrapePublicProfile(username) {
    const url = `${this.baseUrl}/@${username}`;
    try {
      const response = await fetch(url, { headers: this.headers });
      if (response.status === 404) {
        return { status: "not_found" };
      } else if (response.status !== 200) {
        return { status: "error", message: `HTTP ${response.status}` };
      }

      const html = await response.text();

      const titleMatch = html.match(/<meta[^>]*property=["']og:title["'][^>]*content=["']([^"']*)["']/i) || 
                         html.match(/<meta[^>]*content=["']([^"']*)["'][^>]*property=["']og:title["']/i);
      const imageMatch = html.match(/<meta[^>]*property=["']og:image["'][^>]*content=["']([^"']*)["']/i) || 
                         html.match(/<meta[^>]*content=["']([^"']*)["'][^>]*property=["']og:image["']/i);

      let title = titleMatch ? titleMatch[1] : "";
      let image = imageMatch ? imageMatch[1] : "";

      let titleClean = title.replace(/\s*\(@[a-zA-Z0-9_]+\)\s*\|\s*Tinder/i, '').trim();
      titleClean = titleClean.replace(/ - Tinder/i, '').replace(/ \| Tinder/i, '').trim();

      let name = "Hidden";
      let age = "Unknown";

      const titleRegex = /^([^,]+)(?:,\s*(\d+))?/;
      const match = titleClean.match(titleRegex);
      if (match) {
        name = match[1].trim();
        if (match[2]) {
          age = match[2];
        }
      }

      const idMatch = html.match(/"_id":"([a-f0-9]{24})"/);
      let accountId = idMatch ? idMatch[1] : null;
      let creationDate = "Hidden";
      let accountAge = "Unknown";

      if (accountId) {
        try {
          const timestamp = parseInt(accountId.substring(0, 8), 16);
          const dt = new Date(timestamp * 1000);
          creationDate = dt.getUTCFullYear() + '-' + 
                         String(dt.getUTCMonth() + 1).padStart(2, '0') + '-' + 
                         String(dt.getUTCDate()).padStart(2, '0') + ' ' + 
                         String(dt.getUTCHours()).padStart(2, '0') + ':' + 
                         String(dt.getUTCMinutes()).padStart(2, '0') + ':' + 
                         String(dt.getUTCSeconds()).padStart(2, '0') + ' UTC';

          const deltaMs = Date.now() - (timestamp * 1000);
          const totalDays = Math.floor(deltaMs / (1000 * 60 * 60 * 24));
          const years = Math.floor(totalDays / 365);
          const months = Math.floor((totalDays % 365) / 30);
          const days = (totalDays % 365) % 30;

          if (years > 0) {
            accountAge = `${years}y ${months}m ${days}d`;
          } else if (months > 0) {
            accountAge = `${months}m ${days}d`;
          } else {
            accountAge = `${days}d`;
          }
        } catch (err) {
          console.error("Failed to parse MongoDB creation age:", err);
        }
      }

      const robotsMatch = html.match(/<meta[^>]*name=["']robots["'][^>]*content=["']([^"']*)["']/i) || 
                          html.match(/<meta[^>]*content=["']([^"']*)["'][^>]*name=["']robots["']/i);
      let isRestricted = false;
      if (robotsMatch && robotsMatch[1].toLowerCase().includes("noindex")) {
        isRestricted = true;
      }

      return {
        status: "success",
        username,
        name: name || "Hidden",
        age: age || "Unknown",
        birth_date: "Hidden",
        is_restricted: isRestricted,
        image_url: image,
        account_id: accountId || "Hidden",
        account_age: accountAge,
        creation_date: creationDate,
        photos_count: "1+",
        verified: false,
        token_status: "scraping (public)"
      };

    } catch (e) {
      return { status: "error", message: e.message };
    }
  }
}

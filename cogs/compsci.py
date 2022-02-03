import io
import math
import re
from zlib import compress

import discord
import orjson
from discord.ext import commands, menus

from cogs.utils.calculation import bin_float, hex_float, oct_float, safe_eval

TIO_ALIASES = {
    "asm": "assembly-nasm",
    "c": "c-gcc",
    "cpp": "cpp-gcc",
    "c++": "cpp-gcc",
    "cs": "cs-core",
    "java": "java-openjdk",
    "js": "javascript-node",
    "javascript": "javascript-node",
    "ts": "typescript",
    "py": "python3",
    "python": "python3",
    "prolog": "prolog-ciao",
    "swift": "swift4",
}


CODE_REGEX = re.compile(
    r"(?:(?P<lang>^[a-z0-9]+[\ \n])?)(?P<delim>(?P<block>```)|``?)(?(block)"
    r"(?:(?P<alang>[a-z0-9]+)\n)?)(?:[ \t]*\n)*(?P<code>.*?)\s*(?P=delim)",
    re.DOTALL | re.IGNORECASE,
)

RAW_CODE_REGEX = re.compile(
    r"(?:(?P<lang>^[a-z0-9]+[\ \n])?)(?P<code>(?s).*)", re.DOTALL | re.IGNORECASE
)

ANSI = re.compile(r"\x1b\[.*?m")


class LanguageMenu(menus.ListPageSource):
    def __init__(self, data):
        super().__init__(data, per_page=60)

    async def format_page(self, menu, entries):
        msg = ""

        for count, language in enumerate(sorted(entries), start=1):
            if count % 2 == 0:
                msg += f"{language}\n"
            else:
                msg += f"{language:<26}"

        return discord.Embed(color=discord.Color.blurple(), description=f"```{msg}```")


class compsci(commands.Cog):
    """Commands related Computer Science."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.DB = bot.DB

    @commands.command(aliases=["c"])
    async def calc(self, ctx, num_base, *, expr=""):
        """Does math.

        It access to the following basic math functions
        ceil, comb, [fact]orial, gcd, lcm, perm, log, log2,
        log10, sqrt, acos, asin, atan, cos, sin, tain
        and the constants pi, e, tau.

        num_base: str
            The base you want to calculate in.
            Can be hex, oct, bin and for decimal ignore this argument
        expr: str
            A expression to calculate.
        """
        num_bases = {
            "h": (16, hex_float, "0x"),
            "o": (8, oct_float, "0o"),
            "b": (2, bin_float, "0b"),
        }
        base, method, prefix = num_bases.get(num_base[0].lower(), (None, None, None))

        if not base:  # If we haven't been given a base it is decimal
            base = 10
            expr = f"{num_base} {expr}"  # We want the whole expression

        if prefix:
            expr = expr.replace(prefix, "")  # Remove the prefix for a simple regex

        regex = r"[0-9a-fA-F]+" if base == 16 else r"\d+"

        if method:  # No need to extract numbers if we aren't converting
            numbers = [int(num, base) for num in re.findall(regex, expr)]
            expr = re.sub(regex, "{}", expr).format(*numbers)

        result = safe_eval(compile(expr, "<calc>", "eval", flags=1024).body)

        embed = discord.Embed(color=discord.Color.blurple())

        if method:
            embed.description = (
                f"```py\n{expr}\n\n>>> {prefix}{method(result)}\n\nDecimal: {result}```"
            )
            return await ctx.send(embed=embed)

        embed.description = f"```py\n{expr}\n\n>>> {result}```"
        await ctx.send(embed=embed)

    @commands.command()
    async def run(self, ctx, *, code=None):
        """Runs code.

        Examples:
        .run `\u200b`\u200b`\u200bpy
        print("Example")`\u200b`\u200b`\u200b

        .run py print("Example")

        .run py `\u200bprint("Example")`\u200b

        .run py `\u200b`\u200b`\u200bprint("Example")`\u200b`\u200b`\u200b

        code: str
            The code to run.
        """
        if ctx.message.attachments:
            file = ctx.message.attachments[0]
            lang = file.filename.split(".")[-1]
            code = (await file.read()).decode()
        elif match := list(CODE_REGEX.finditer(code)):
            code, lang, alang = match[0].group("code", "lang", "alang")
            lang = lang or alang
        elif match := list(RAW_CODE_REGEX.finditer(code)):
            code, lang = match[0].group("code", "lang")

        if not lang:
            return await ctx.reply(
                embed=discord.Embed(
                    color=discord.Color.blurple(),
                    description="```You need to supply a language"
                    " either as an arg or inside a codeblock```",
                )
            )

        lang = lang.strip()

        if lang not in orjson.loads(self.DB.main.get(b"aliases")):
            lang = lang.replace("`", "`\u200b")
            return await ctx.reply(
                embed=discord.Embed(
                    color=discord.Color.blurple(),
                    description=f"```No support for language {lang}```",
                )
            )

        data = {
            "language": lang,
            "version": "*",
            "files": [{"content": code}],
        }

        async with ctx.typing(), self.bot.client_session.post(
            "https://emkc.org/api/v2/piston/execute", data=orjson.dumps(data)
        ) as response:
            data = await response.json()

        output = data["run"]["output"]

        if "compile" in data and data["compile"]["stderr"]:
            output = data["compile"]["stderr"] + "\n" + output

        if not output:
            return await ctx.reply(
                embed=discord.Embed(
                    color=discord.Color.blurple(), description="```No output```"
                )
            )

        output = output.replace("`", "`\u200b")
        if len(output) + len(lang) > 1993:
            return await ctx.reply(file=discord.File(io.StringIO(output), "output.txt"))

        await ctx.reply(f"```{lang}\n{output}```")

    @commands.command()
    async def languages(self, ctx):
        """Shows the languages that the run command can use."""
        languages = orjson.loads(self.DB.main.get(b"languages"))

        msg = ""

        for count, language in enumerate(sorted(languages), start=1):
            if count % 4 == 0:
                msg += f"{language}\n"
            else:
                msg += f"{language:<13}"

        embed = discord.Embed(color=discord.Color.blurple(), description=f"```{msg}```")
        await ctx.send(embed=embed)

    @commands.command()
    async def tio(self, ctx, *, code):
        """Uses tio.run to run code.

        Examples:
        .tio `\u200b`\u200b`\u200bpy
        print("Example")`\u200b`\u200b`\u200b

        .tio py print("Example")

        .tio py `\u200bprint("Example")`\u200b

        .tio py `\u200b`\u200b`\u200bprint("Example")`\u200b`\u200b`\u200b

        code: str
            The code to run.
        """
        if ctx.message.attachments:
            file = ctx.message.attachments[0]
            lang = file.filename.split(".")[-1]
            code = (await file.read()).decode()
        elif match := [*CODE_REGEX.finditer(code)]:
            code, lang, alang = match[0].group("code", "lang", "alang")
            lang = lang or alang
        elif match := [*RAW_CODE_REGEX.finditer(code)]:
            code, lang = match[0].group("code", "lang")

        if not lang:
            return await ctx.reply(
                embed=discord.Embed(
                    color=discord.Color.blurple(),
                    description="```You need to supply a language"
                    " either as an arg or inside a codeblock```",
                )
            )

        lang = lang.strip()
        lang = TIO_ALIASES.get(lang, lang)  # tio doesn't have default aliases

        if lang not in orjson.loads(self.DB.main.get(b"tiolanguages")):
            return await ctx.reply(
                embed=discord.Embed(
                    color=discord.Color.blurple(),
                    description=f"```No support for language {lang}```",
                )
            )

        url = "https://tio.run/cgi-bin/run/api/"

        data = compress(
            f"Vlang\x001\x00{lang}\x00F.code.tio\x00{len(code)}\x00{code}\x00R".encode(),
            9,
        )[2:-4]

        async with ctx.typing(), self.bot.client_session.post(
            url, data=data
        ) as response:
            response = (await response.read()).decode("utf-8")
            response = response.replace(response[:16], "")

        await ctx.reply(f"```{lang}\n{response}```")

    @commands.command()
    async def tiolanguages(self, ctx):
        """Shows all the languages that tio.run can handle."""
        languages = orjson.loads(self.DB.main.get(b"tiolanguages"))

        pages = menus.MenuPages(
            source=LanguageMenu(languages),
            clear_reactions_after=True,
            delete_message_after=True,
        )
        await pages.start(ctx)

    @commands.command()
    async def hello(self, ctx, language):
        """Gets the code for hello world in a language.

        language: str
        """
        language = TIO_ALIASES.get(language, language)
        data = orjson.loads(self.DB.main.get(b"helloworlds"))
        code = data.get(language)

        embed = discord.Embed(color=discord.Color.blurple())

        if not code:
            embed.description = "```Language not found.```"
            return await ctx.send(embed=embed)

        embed.description = f"```{language}\n{code}```"
        await ctx.send(embed=embed)

    @commands.command()
    async def dashboard(self, ctx):
        """Sends a link to Bryns dashboard."""
        await ctx.send("https://web.tukib.org/uoa")

    @commands.command()
    async def notes(self, ctx):
        """Sends a link to Joes notes."""
        embed = discord.Embed(color=discord.Color.blurple(), title="Joes Notes")

        embed.description = """
        [Home Page](https://notes.joewuthrich.com)

        [Compsci 101](https://notes.joewuthrich.com/compsci101)
        Introduction to programming using the Python programming language.

        [Compsci 110](https://notes.joewuthrich.com/compsci110)
        This course explains how computers work and some of the things we can use them for.

        [Compsci 120](https://notes.joewuthrich.com/compsci120)
        Introduces basic mathematical tools and methods needed for computer science.

        [Compsci 130](https://notes.joewuthrich.com/compsci130)
        Entry course to Computer Science for students with prior programming knowledge in Python.

        [Compsci 225](https://notes.joewuthrich.com/compsci225)
        Discrete Structures in Mathematics and Computer Science.
        """
        await ctx.send(embed=embed)

    @commands.group(name="float", invoke_without_command=True)
    async def _float(self, ctx, number: float):
        """Converts a float to the half-precision floating-point format.

        number: float
        """
        decimal = abs(number)

        sign = 1 - (number >= 0)
        mantissa = math.floor(
            decimal * 2 ** math.floor(math.log2(0b111111111 / decimal))
        )
        exponent = math.floor(math.log2(decimal) + 1)
        exponent_sign, exponent = 1 - (exponent >= 0), abs(exponent)

        bin_exponent = 0
        shifted_num = number

        while shifted_num != int(shifted_num):
            shifted_num *= 2
            bin_exponent += 1

        if not bin_exponent:
            binary = standard = f"{int(number):b}"
        else:
            standard = f"{int(shifted_num):0{bin_exponent + 1}b}"
            binary = (
                f"{standard[:-bin_exponent]}.{standard[-bin_exponent:].rstrip('0')}"
            )

        binary = binary[: max(binary.find("1") + 1, 12)]

        embed = discord.Embed(color=discord.Color.blurple())
        embed.add_field(name="Decimal", value=number)
        embed.add_field(
            name="Binary",
            value=binary,
        )
        embed.add_field(name="\u200b", value="\u200b")
        embed.add_field(
            name="Standard Form", value=f"{standard.lstrip('0')[:9]:0>9} x 2^{exponent}"
        )
        embed.add_field(
            name="Result",
            value=f"{(sign << 15) | (mantissa << 6) | (exponent_sign << 5) | exponent:X}",
        )
        embed.add_field(name="\u200b", value="\u200b")

        sign, mantissa, exponent_sign, exponent = (
            f"{sign:b}",
            f"{mantissa:0>9b}",
            f"{exponent_sign:b}",
            f"{exponent:0>5b}",
        )

        embed.add_field(
            name="Mantissa Sign   Mantissa   Exponent Sign   Exponent",
            value=f"`{sign:^13s}{mantissa:^11s}{exponent_sign:^13s} {exponent:^9s}`",
        )

        return await ctx.send(embed=embed)

    @_float.command(name="decode", aliases=["d"])
    async def _decode(self, ctx, number):
        """Decodes a float from the half-precision floating-point format.

        number: str
        """
        number = int(number, 16)

        sign = (number & 32768) >> 15
        mantissa = (number & 32704) >> 6
        exponent_sign = (number & 32) >> 5
        exponent = number & 31
        float_value = (
            (sign * -2 + 1) * mantissa * 2 ** (-9 + (exponent_sign * -2 + 1) * exponent)
        )
        sign, mantissa, exponent_sign, exponent = (
            f"{sign:b}",
            f"{mantissa:0>9b}",
            f"{exponent_sign:b}",
            f"{exponent:0>5b}",
        )
        embed = discord.Embed(color=discord.Color.blurple())
        embed.add_field(name="Decimal", value=float_value)
        embed.add_field(name="Binary", value=bin_float(float_value))
        embed.add_field(name="\u200b", value="\u200b")
        embed.add_field(
            name="Mantissa Sign   Mantissa   Exponent Sign   Exponent",
            value=f"`{sign:^13s}{mantissa:^11s}{exponent_sign:^13s} {exponent:^9s}`",
        )
        return await ctx.send(embed=embed)

    @commands.command(name="hex")
    async def _hex(self, ctx, number):
        """Shows a number in hexadecimal prefixed with “0x”.

        number: str
            The number you want to convert.
        """
        try:
            hexadecimal = hex_float(float(number))
        except (ValueError, OverflowError):
            hexadecimal = "failed"
        try:
            decimal = int(number, 16)
        except ValueError:
            decimal = "failed"

        await ctx.send(
            embed=discord.Embed(
                color=discord.Color.blurple(),
                description=f"```py\nhex: {hexadecimal}\nint: {decimal}```",
            )
        )

    @commands.command(name="oct")
    async def _oct(self, ctx, number):
        """Shows a number in octal prefixed with “0o”.

        number: str
            The number you want to convert.
        """
        try:
            octal = oct_float(float(number))
        except (ValueError, OverflowError):
            octal = "failed"
        try:
            decimal = int(number, 8)
        except ValueError:
            decimal = "failed"

        await ctx.send(
            embed=discord.Embed(
                color=discord.Color.blurple(),
                description=f"```py\noct: {octal}\nint: {decimal}```",
            )
        )

    @commands.command(name="bin")
    async def _bin(self, ctx, number):
        """Shows a number in binary prefixed with “0b”.

        number: str
            The number you want to convert.
        """
        try:
            binary = bin_float(float(number))
        except (ValueError, OverflowError):
            binary = "failed"

        whole, *frac = number.split(".")
        try:
            decimal = int(whole, 2)

            for i, digit in enumerate(frac[0], start=1):
                if digit == "1":
                    decimal += 0.5**i
                elif digit != "0":
                    decimal = "failed"
                    break
        except ValueError:
            decimal = "failed"

        await ctx.send(
            embed=discord.Embed(
                color=discord.Color.blurple(),
                description=f"```py\nbin: {binary}\nint: {decimal}```",
            )
        )

    @commands.group()
    async def cipher(self, ctx):
        """Solves or encodes a caesar cipher."""
        if not ctx.invoked_subcommand:
            embed = discord.Embed(
                color=discord.Color.blurple(),
                description=f"```Usage: {ctx.prefix}cipher [decode/encode]```",
            )
            await ctx.send(embed=embed)

    @cipher.command()
    async def encode(self, ctx, shift: int, *, message):
        """Encodes a message using the caesar cipher.

        shift: int
            How much you want to shift the message.
        message: str
        """
        if message.isupper():
            chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        else:
            message = message.lower()
            chars = "abcdefghijklmnopqrstuvwxyz"

        table = str.maketrans(chars, chars[shift:] + chars[:shift])

        await ctx.send(message.translate(table))

    @cipher.command(aliases=["solve", "brute"])
    async def decode(self, ctx, *, message):
        """Solves a caesar cipher via brute force.
        Shows results sorted by the chi-square of letter frequencies

        message: str
        """
        if message.isupper():
            chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        else:
            message = message.lower()
            chars = "abcdefghijklmnopqrstuvwxyz"

        # fmt: off

        freq = {
            "a": 8.04, "b": 1.48, "c": 3.34,
            "d": 3.82, "e": 12.49, "f": 2.4,
            "g": 1.87, "h": 5.05, "i": 7.57,
            "j": 0.16, "k": 0.54, "l": 4.07,
            "m": 2.51, "n": 7.23, "o": 7.64,
            "p": 2.14, "q": 0.12, "r": 6.28,
            "s": 6.51, "t": 9.28, "u": 2.73,
            "v": 1.05, "w": 1.68, "x": 0.23,
            "y": 1.66, "z": 0.09,
        }

        # fmt: on

        msg_len = len(message)

        rotate1 = str.maketrans(chars, chars[1:] + chars[0])
        embed = discord.Embed(color=discord.Color.blurple())

        results = []

        for i in range(25, 0, -1):
            message = message.translate(rotate1)
            chi = sum(
                [
                    (((message.count(char) / msg_len) - freq[char]) ** 2) / freq[char]
                    for char in set(message.lower().replace(" ", ""))
                ]
            )
            results.append((chi, (i, message)))

        for chi, result in sorted(results, reverse=True):
            embed.add_field(name=result[0], value=result[1])

        embed.set_footer(text="Sorted by the chi-square of their letter frequencies")

        await ctx.send(embed=embed)

    @commands.command()
    async def block(self, ctx, A, B):
        """Solves a block cipher in the format of a python matrix.

        e.g
        "1 2 3" "3 7 15, 6 2 61, 2 5 1"

        A: str
        B: str
        """

        def starmap(iterable):
            for num1, num2 in iterable:
                yield num1 * num2

        if A > "a":
            A = [[ord(letter) - 97 for letter in A]]
        else:
            A = A.split(",")
            A = [[int(num) for num in block.split()] for block in A]
        B = B.split(",")
        B = [[int(num) for num in block.split()] for block in B]

        results = ""

        for block in A:
            results += f"{[sum(starmap(zip(block, col))) for col in zip(*B)]}\n"

        embed = discord.Embed(
            color=discord.Color.blurple(), description=f"```{results}```"
        )
        await ctx.send(embed=embed)

    @commands.group()
    async def binary(self, ctx):
        """Encoded or decodes binary as ascii text."""
        if not ctx.invoked_subcommand:
            embed = discord.Embed(
                color=discord.Color.blurple(),
                description=f"```Usage: {ctx.prefix}binary [decode/encode]```",
            )
            await ctx.send(embed=embed)

    @binary.command(name="en")
    async def binary_encode(self, ctx, *, text):
        """Encodes ascii text as binary.

        text: str
        """
        await ctx.send(" ".join([f"{bin(ord(letter))[2:]:0>8}" for letter in text]))

    @binary.command(name="de")
    async def binary_decode(self, ctx, *, binary):
        """Decodes binary as ascii text.

        binary: str
        """
        binary = binary.replace(" ", "")
        # fmt: off
        await ctx.send(
            "".join([chr(int(binary[i: i + 8], 2)) for i in range(0, len(binary), 8)])
        )
        # fmt: on

    @commands.command()
    async def ones(self, ctx, number: int, bits: int):
        """Converts a decimal number to binary ones complement.

        number: int
        """
        table = {49: "0", 48: "1"}
        sign = 1 - (number >= 0)
        return await ctx.send(
            embed=discord.Embed(
                color=discord.Color.blurple(),
                description=f"```{sign}{f'{abs(number):0>{bits-1}b}'.translate(table)}```",
            )
        )

    @commands.command()
    async def twos(self, ctx, number: int, bits: int):
        """Converts a decimal number to binary twos complement.

        number: int
        bits: int
        """
        return await ctx.send(
            embed=discord.Embed(
                color=discord.Color.blurple(),
                description=f"```{number & (2 ** bits - 1):0>{bits}b}```",
            )
        )

    @commands.group()
    async def rle(self, ctx):
        """Encodes or decodes a string with run length encoding."""
        if not ctx.invoked_subcommand:
            embed = discord.Embed(
                color=discord.Color.blurple(),
                description=f"```Usage: {ctx.prefix}rle [de/en]```",
            )
            await ctx.send(embed=embed)

    @rle.command()
    async def en(self, ctx, *, text):
        """Encodes a string with run length encoding."""
        text = re.sub(r"(.)\1*", lambda m: m.group(1) + str(len(m.group(0))), text)
        await ctx.send(text)

    @rle.command()
    async def de(self, ctx, *, text):
        """Decodes a string with run length encoding."""
        text = re.sub(r"(\D)(\d+)", lambda m: int(m.group(2)) * m.group(1), text)
        await ctx.send(text)

    @commands.command(aliases=["ch", "cht"])
    async def cheatsheet(self, ctx, *search):
        """https://cheat.sh/python/ gets a cheatsheet.

        search: tuple
            The search terms.
        """
        search = "+".join(search)

        url = f"https://cheat.sh/python/{search}"
        headers = {"User-Agent": "curl/7.68.0"}

        async with ctx.typing(), self.bot.client_session.get(
            url, headers=headers
        ) as page:
            result = ANSI.sub("", await page.text()).translate({96: "\\`"})

        embed = discord.Embed(
            title=f"https://cheat.sh/python/{search}",
            color=discord.Color.blurple(),
            description=f"```py\n{result}```",
        )

        await ctx.send(embed=embed)


def setup(bot: commands.Bot) -> None:
    """Starts the compsci cog."""
    bot.add_cog(compsci(bot))
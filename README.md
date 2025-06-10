# MangaDex Follows Exporter

A script to export all your MangaDex follows.

---

## Do I really have to enter my credentials?

Yes.

For MangaDex, your followed titles are private, to be able to export them the script needs to be able to access your account on your behalf.

For MangaUpdates, adding entries to your reading list requires the script to access MangaUpdates' APIs while authenticating as you.

In neither cases your credentials leave your computer, you can check the code yourself if you don't believe me (which you shouldn't).

Without providing your credentials the script will not be able to do its job and will not work.

---

## Where can the script export to?

The script can export to

* a CSV file;
* an Excel file;
* MangaUpdates' reading list.

The MangaUpdates exporter synchronises only the titles, not the last read chapter. The chapter synchronisation is a planned feature.

MyAnimeList and AniList are not currently implemented, plans for future integrations are not certain.

---

## Before you run the script

To be able to pull your follows from MangaDex it's not enough having your credentials, you need what they call a "Personal API Client".

To procure one, follow the steps below.

1. Log into MangaDex.
2. Go to your [account settings page].
3. Click on the "API Client" entry on the left.
4. Click on the "Create" button on the right.
5. Enter a name (required) and a description (optional) of your choosing.
6. Wait a minute or two while the system approves your client.
7. Reload the page (e.g. by pressing F5 or CTRL-R).
8. Check if besides the entry you just created a green dot is shown.
9. Click on the entry you created.
10. Copy the value you see on the right of the "active" label.
11. Paste the value you just copied somewhere, this is your MangaDex `client_id` value for later.
12. Click on the "Get secret" button.
13. Click on the "Copy secret" button.
14. Paste the value you just copied somewhere, this is your `client_secret` value for later.

**Do not** share your `client_id` and `client_secret` with *anyone*, they are your personal access codes for MangaDex's APIs.

If in step 8 the dot is not green, either try waiting a couple of minutes more and then reloading the page again or contact the MangaDex's staff asking why the client is not approved.

---

## How to run the script

You can either download and run a prebuilt binary (only for Microsoft Windows) or run the script yourself.

The prebuilt binary is more user-friendly and does not require you to install or fiddle with anything, but you have to trust me since you will not see what the application does.

The script requires you to have a working Python environment and to know your way around a command line, but you can see everything the script is doing.

---

## How to use the prebuilt binary

1. From the [latest release] download the `MangaDexFollowsExporter.vX.X.X.zip` file.
2. Extract the file you downloaded somewhere.
3. Open the directory where you extracted the file to.
4. Open the `configuration.ini` file with a text editor.
   * Microsoft Word is __not__ a text editor, use Notepad.
5. Fill in the various values.
   * The entries in the `mangadex` section are mandatory.
   * The entries in the `mangaupdates` section are required only if you want to use the MangaUpdates exporter.
6. Save and close the `configuration.ini` file.
7. Run the file `mangadex_follows_exporter.exe`.
8. Answer to the questions asking you which exporters you want to use.
   * Answer `y` (yes) to enable the exporter.
   * Answer `n` (no) to *not* enable the exporter.
   * Multiple exporter can be enabled at the same time.
9. Wait for the process to complete.
10. If you don't plan to use the application again delete the MangaDex API Client you created earlier. 

If you enabled the CSV or Excel exporters you will find the generated files alongside the `mangadex_follows_exporter.exe` file.

---

## How to use the source code

The code requires a working Python environment, I'm using Python 3.13.

1. Check out or download the project somewhere.
2. Create a virtual environment (e.g. `python -m venv .venv`).
3. Activate the virtual environment (e.g. `".venv\scripts\activate.bat"`).
4. Restore the libraries (e.g. `python -m pip install -r requirements.txt`).
5. Configure the values in the `configuration.ini` file.
6. Run the application (e.g. `python src\mangadex_follows_exporter.py`).

---

## If something goes wrong

Either [create a new issue] or write a comment on the Reddit post explaining your problem.

You *must* include the full text of the error if one is shown.

Other useful information:

* how many follows you have in MangaDex;
* what exporters have you enabled;
* if the problem happens every time;
* anything else you can think would be useful.

---

## Sources

* https://api.mangadex.org/docs/
* https://api.mangadex.org/docs/redoc.html
* https://api.mangadex.org/docs/swagger.html
* https://api.mangaupdates.com/

---

## License

The project is published under the [MIT License].

    MIT License

    Copyright (c) 2025 Sassy Lily

    Permission is hereby granted, free of charge, to any person obtaining a copy
    of this software and associated documentation files (the "Software"), to deal
    in the Software without restriction, including without limitation the rights
    to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
    copies of the Software, and to permit persons to whom the Software is
    furnished to do so, subject to the following conditions:

    The above copyright notice and this permission notice shall be included in all
    copies or substantial portions of the Software.

    THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
    IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
    FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
    AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
    LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
    OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
    SOFTWARE.

---

## Credits

The MangaUpdates exporter uses [henrik9999]'s [mappings file] to convert the old MangaUpdates IDs exposed by MangaDex in their new IDs.

[account settings page]: <https://mangadex.org/settings>
[latest release]: <https://github.com/sassy-lily/mangadex-follows-exporter/releases/latest>
[create a new issue]: <https://github.com/sassy-lily/mangadex-follows-exporter/issues>
[MIT License]: <https://choosealicense.com/licenses/mit/>
[henrik9999]: <https://github.com/henrik9999>
[mappings file]: <https://github.com/henrik9999/mangaupdates-old-id-mapping>

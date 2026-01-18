# Book Site

This code provides creates a static website to read a book (e.g., a novel or technical book) online. The experience is designed to be similar to using an e-reader, with features such as:

* Table of contents for easy navigation
* Current position tracking
* Support for dark mode
* Responsive design for various screen sizes

The idea is not to be too complicated, just provide a simple and pleasant reading experience.

## Usage

You can build the demo book site by running:

```
python3 build.py demo/book.toml -o built
```

Which will create a static website in the `built` directory. You can then serve this directory using any static file server, such as `python3 -m http.server`:

```
cd built && python3 -m http.server 8000
```

Or use a `file://` URL to open `index.html` directly in your browser (although features like local storage may not work properly in that case).

## Sites Using This

The book site for the fan-fiction novel [_Phoenix_](https://phoenix.team-us.org/) uses this code.  It seems to be working well there.

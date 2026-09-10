/* global phantom: false */

var page = require( "webpage" ).create(),
	system = require( "system" ),
	testUrl = system.args[ 1 ],
	completed = false,
	pageError = false,
	timeout;

function exit( code ) {
	if ( completed ) {
		return;
	}
	completed = true;
	clearTimeout( timeout );
	phantom.exit( code );
}

if ( !testUrl ) {
	console.error( "Usage: phantomjs test/runner.js URL" );
	phantom.exit( 1 );
} else {
	page.onConsoleMessage = function( message ) {
		console.log( message );
	};

	page.onError = function( message, trace ) {
		pageError = true;
		console.error( "Browser error: " + message );
		trace.forEach( function( frame ) {
			console.error( "  " + frame.file + ":" + frame.line );
		} );
	};

	page.onCallback = function( result ) {
		var exitCode = pageError || result.failed || result.total === 0 ? 1 : 0;

		console.log(
			"QUnit: " + result.passed + " passed, " + result.failed +
			" failed, " + result.total + " total"
		);
		exit( exitCode );
	};

	timeout = setTimeout( function() {
		console.error( "QUnit did not complete" );
		exit( 1 );
	}, 120000 );

	page.open( testUrl, function( status ) {
		var registered;

		if ( status !== "success" ) {
			console.error( "Unable to open " + testUrl );
			exit( 1 );
			return;
		}

		registered = page.evaluate( function() {
			if ( !window.QUnit || !QUnit.done ) {
				return false;
			}

			QUnit.log( function( details ) {
				if ( !details.result ) {
					console.error(
						"QUnit assertion failed: module=" + details.module +
						", name=" + details.name + ", message=" + details.message +
						", actual=" + details.actual + ", expected=" + details.expected
					);
				}
			} );

			QUnit.done( function( details ) {
				window.callPhantom( {
					passed: details.passed,
					failed: details.failed,
					total: details.total
				} );
			} );
			return true;
		} );

		if ( !registered ) {
			console.error( "QUnit was not available" );
			exit( 1 );
		}
	} );
}
